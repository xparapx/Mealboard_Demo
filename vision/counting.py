"""라인크로싱·처리율·기준점 — 순수 함수. 카메라·모델·DB 를 모른다(PC 에서 그대로 테스트된다).

카운팅 규칙(CLAUDE.md §2): 사람의 기준점은 bbox 바닥 중앙. ROI 출구변(λ선 = roi.lambda_edge) 을 기준점이 넘어가면 '배식대 통과' 1명.
넘어감 판정은 선에 대한 부호 변화이되, 선 양쪽 ±buffer_px 완충띠 안에서는 판정을 미룬다 — 경계에서 떨리는 트랙이 1명을 여러 번 세지 않게.
out_dir 은 zones.json 의 약속 그대로: 1 이면 λ선 i→j 의 왼쪽(이미지 좌표 y 아래 방향 기준 외적 > 0)이 출구, -1 이면 오른쪽."""
from collections import deque


def foot_of_bbox(x1, y1, x2, y2):
    """bbox → 기준점(바닥 중앙)"""
    return (x1 + x2) / 2, y2


def cross(a, b, p):
    """(b-a) × (p-a). 관리 편집기(zones-editor.js)와 같은 부호 약속 — >0 이면 i→j 의 왼쪽"""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def signed_dist(a, b, p):
    """점 p 의 선 a→b 에 대한 부호 있는 거리(같은 단위). 선이 점이면 0"""
    L = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
    return 0.0 if L == 0 else cross(a, b, p) / L


class LineCounter:
    """트랙 ID 별로 '마지막으로 확정된 쪽'을 기억하고, 반대쪽으로 확정되는 순간만 센다.
    update() → +1: 출구 쪽으로 넘어감(배식 완료), -1: 다시 안쪽으로, 0: 변화 없음(또는 완충띠 안)"""

    def __init__(self, a, b, out_dir=1, buffer=20.0):
        self.a, self.b, self.out_dir, self.buffer = tuple(a), tuple(b), 1 if out_dir >= 0 else -1, float(buffer)
        self.side = {}
        self.seen = {}                                          # tid → 마지막 관측 시각(유예 forget 용, 09-28)

    def update(self, tid, p, t=None):
        if t is not None:
            self.seen[tid] = t
        d = signed_dist(self.a, self.b, p) * self.out_dir      # >0 = 출구 쪽
        if abs(d) < self.buffer:
            return 0                                            # 완충띠 — 판정을 미룬다(기억은 그대로)
        s = 1 if d > 0 else -1
        prev = self.side.get(tid)
        self.side[tid] = s
        if prev is None or prev == s:
            return 0
        return s

    def forget(self, alive, t=None, grace=0.0):
        """사라진 트랙의 기억을 지운다. 09-28: ByteTrack 은 매칭 실패 트랙을 결과에 내보내지 않으므로 한 프레임만 가려져도
        alive 에서 빠진다 — grace 초 동안은 기억을 유지해 복귀한 같은 ID 의 부호(=통과 판정)가 이어지게 한다(t 없으면 즉시)"""
        alive = set(alive)
        for tid in [k for k in self.side if k not in alive]:
            if t is None or t - self.seen.get(tid, t) >= grace:
                del self.side[tid]
                self.seen.pop(tid, None)

    def reset(self):
        self.side.clear()
        self.seen.clear()


class DwellTracker:
    """트랙별 '실제 대기시간' 실측(09-16 사용자 결정, 자동 보정 B안) — ROI 진입 시각과 그 순간의 예측 대기를 기억했다가
    λ선 통과 순간 (체류시간, 진입 시점 예측) 이벤트를 남긴다. 이벤트는 이동 창 안 요약(중앙값·보정계수)으로만 쓰이고
    개인 단위로는 어디에도 저장되지 않는다(§2 원칙 — DB 에는 창 요약 숫자만).

    보정계수 K = median(실제 체류 ÷ 진입 시점 예측), CLAMP 안으로 누른다. 화면 대기 = Little 원시값 × K.
    한계(기록): 가림으로 트랙 ID 가 끊기면 체류가 짧게 측정된다 — MIN_DWELL_SEC 미만은 버리고 중앙값으로 완충."""

    MIN_DWELL_SEC = 20.0        # 이보다 짧은 체류는 트랙 재부여·선 근처 출생으로 본다(실측에서 제외)
    MIN_EVENTS = 5              # 이만큼 모여야 K 를 낸다 — 그 전에는 보정하지 않는다(K=None)
    MIN_PRED_MIN = 0.5          # 진입 예측이 이보다 작으면 비율이 폭주한다 — 그 이벤트는 체류 실측에만 쓴다
    CLAMP = (0.5, 3.0)

    def __init__(self, window_sec=900, bias=1.0):
        self.window = float(window_sec)
        self.bias = float(bias)     # 체류 과소 편향 보정(09-17, .env DWELL_BIAS): 트랙 끊김으로 실측이 짧게 재진다 —
        self.entries = {}           # 수동 실측 대조(12:44 실제 1.3분 vs 자동 0.9분 ≈ ×1.4)로 정한 배율, 실측이 쌓이면 조정
        self.seen = {}              # tid → 마지막 관측 시각(유예 forget 용, 09-28)
        self.events = deque()       # (통과 t, 보정된 체류 초, 비율 또는 None)

    def observe(self, tid, in_roi, t, predicted_min):
        """프레임마다 부른다 — ROI 안에서 처음 보인 트랙의 진입을 기억한다(깜빡임으로 잠깐 나가도 리셋하지 않는다 — forget 의 grace 가 보장)"""
        self.seen[tid] = t
        if in_roi and tid not in self.entries:
            self.entries[tid] = (t, predicted_min)

    def crossed(self, tid, t):
        """λ선 통과(출구 방향) — 체류 이벤트를 남기고 체류 초를 돌려준다. 진입 기록이 없거나 너무 짧으면 None"""
        ent = self.entries.pop(tid, None)
        if ent is None:
            return None
        dwell = t - ent[0]
        if dwell < self.MIN_DWELL_SEC:              # 필터는 날것 기준 — 편향 배율로 문턱이 흔들리지 않게
            return None
        dwell *= self.bias
        pred = ent[1]
        ratio = (dwell / 60) / pred if pred is not None and pred >= self.MIN_PRED_MIN else None
        self.events.append((t, dwell, ratio))
        return dwell

    def forget(self, alive, t=None, grace=0.0):
        """09-28: 한 프레임 누락에도 진입 기록을 즉시 지우던 것이 체류 이벤트 0건의 직접 원인 — grace 초 안에 복귀하면 유지"""
        alive = set(alive)
        for tid in [k for k in self.entries if k not in alive]:
            if t is None or t - self.seen.get(tid, t) >= grace:
                del self.entries[tid]
                self.seen.pop(tid, None)

    def stats(self, t):
        """이동 창 요약 → {n, measured_min, k}. measured_min = 체류 중앙값(분), k = 비율 중앙값(클램프) 또는 None"""
        while self.events and self.events[0][0] < t - self.window:
            self.events.popleft()
        dwells = sorted(e[1] for e in self.events)
        ratios = sorted(e[2] for e in self.events if e[2] is not None)
        med = (lambda v: v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2)
        measured = round(med(dwells) / 60, 1) if dwells else None
        k = None
        if len(ratios) >= self.MIN_EVENTS:
            k = round(min(max(med(ratios), self.CLAMP[0]), self.CLAMP[1]), 2)
        return {"n": len(dwells), "measured_min": measured, "k": k}

    def reset(self):
        self.entries.clear()
        self.seen.clear()
        self.events.clear()


def _median(v):
    v = sorted(v)
    n = len(v)
    return None if not n else (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)


class FifoEstimator:
    """개별 추적 없이 실제 대기시간을 재는 누적곡선(Newell) 추정기 — 09-28 도입(제안서 P1). 트랙 ID 가 이어지지 않아도 되고
    사람 수만 쓴다(개인 정보 없음). 표본 틱마다 add(t, L, served_net) 를 부른다:
      누적 출발 D(t) += 순통과 수,  누적 도착 A(t) = max(A(t-1), D(t) + L(t))   (인원 보존·단조)
    선착순(FIFO)이면 'N 번째 통과자 = N 번째 진입자' 이므로, 이번 틱에 통과한 사람의 대기 = t − (A 가 D 에 처음 닿은 시각).
    이벤트는 DwellTracker 와 같은 모양의 이동 창 요약(체류 중앙값·K)으로만 쓰인다. 새치기·합류로 순서가 섞이면 개별 값에
    오차가 생기지만 중앙값이 흡수한다. 한계: L 의 편향(화각 밖 꼬리)은 그대로 전달된다 — 그건 커버리지 문제로 따로 푼다."""

    MIN_EVENTS = 5
    MIN_PRED_MIN = 0.5
    CLAMP = (0.5, 3.0)
    MAX_ARRIVALS = 4000            # 도착 곡선 점 상한(10초 틱 ≈ 11시간) — 창 전환 때 reset 되므로 실제로는 닿지 않는다

    def __init__(self, window_sec=900):
        self.window = float(window_sec)
        self.reset()

    def add(self, t, queue_len, served_net, predicted_min=None):
        """t 단조 초, queue_len = 이번 틱의 L, served_net = 직전 틱 이후 순통과 수(출구 +1·복귀 −1 합, 음수는 0), predicted_min = 이 순간의 원시 예측.
        통과가 있었으면 그 사람들의 대기시간 이벤트를 남기고 마지막 대기(초)를 돌려준다(없으면 None)"""
        n = max(0, int(served_net or 0))
        if self.t_first is None:
            self.t_first = t
        self.D += n
        A = max(self.A, self.D + max(0, int(queue_len or 0)))
        if A > self.A:                                          # 새로 진입한 사람들: (진입 시각, 그때까지의 누적 도착, 그 순간 예측)
            self.arrivals.append((t, A, predicted_min))
            if len(self.arrivals) > self.MAX_ARRIVALS:
                self.arrivals.popleft()
            self.A = A
        last = None
        if n:
            # D 번째 진입자가 들어온 시각 = 누적 도착이 D 에 처음 닿은 점. 통과 n 명 각각(D-n+1 … D)에 대해 이벤트를 남긴다
            for k in range(self.D - n + 1, self.D + 1):
                while self.arrivals and self.arrivals[0][1] < k:
                    self.arrivals.popleft()                     # 누적 도착이 k 미만인 점은 이후 어떤 통과자에게도 필요 없다(k 단조 증가)
                if not self.arrivals:
                    continue                                    # 도착 곡선이 아직 k 에 못 미침(L 이 0 인데 통과가 났다 — 화각 밖 진입)
                t_in, _, pred = self.arrivals[0]
                if t_in >= t or t_in == self.t_first:
                    continue                                    # 이번 틱에 추론된 진입(L 에 없던 통과자)·첫 틱의 기존 대기자 — 진입 시각 미상이라 버린다
                                                                # (첫 틱 제외는 09-28 실측: 재시작 직후 K 0.5 로 눌리던 잔상의 원인)
                wait = t - t_in
                ratio = (wait / 60) / pred if pred is not None and pred >= self.MIN_PRED_MIN else None
                self.events.append((t, wait, ratio))
                last = wait
        return last

    def stats(self, t):
        """이동 창 요약 → {n, measured_min, k} — DwellTracker.stats 와 같은 모양"""
        while self.events and self.events[0][0] < t - self.window:
            self.events.popleft()
        dwells = [e[1] for e in self.events]
        ratios = [e[2] for e in self.events if e[2] is not None]
        measured = round(_median(dwells) / 60, 1) if dwells else None
        k = None
        if len(ratios) >= self.MIN_EVENTS:
            k = round(min(max(_median(ratios), self.CLAMP[0]), self.CLAMP[1]), 2)
        return {"n": len(dwells), "measured_min": measured, "k": k}

    def reset(self):
        self.A = 0
        self.D = 0
        self.t_first = None        # 첫 틱 시각 — 그때 이미 서 있던 인원은 진입 시각을 모른다
        self.arrivals = deque()    # (t, 누적 도착 A, 그 순간 예측)
        self.events = deque()      # (통과 t, 대기 초, 비율 또는 None)


class MedianWindow:
    """시간 창 안 값들의 중앙값 — 표본 평활(09-17 사용자 결정: 검출 깜빡임이 화면 숫자에 1:1 로 전달되던 것을 완화).
    L 은 짧은 창(약 25초)으로 한두 프레임 끊겨도 0 으로 꺼지지 않게, 공표 대기는 90초 창으로 추세만 남긴다. None 은 넣지 않는다"""

    def __init__(self, window_sec):
        self.window = float(window_sec)
        self.items = deque()            # (t, v)

    def add(self, t, v):
        if v is not None:
            self.items.append((t, v))

    def median(self, t):
        while self.items and self.items[0][0] < t - self.window:
            self.items.popleft()
        v = sorted(x for _, x in self.items)
        if not v:
            return None
        n = len(v)
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

    def reset(self):
        self.items.clear()


class RateWindow:
    """통과 이벤트의 이동합 → 명/분. 창 길이는 호출자가 준다(운영은 .env RATE_WINDOW_SEC, 기본 2분 — 09-16 사용자 결정). 시각은 단조 초"""

    def __init__(self, window_sec=300):
        self.window = float(window_sec)
        self.events = deque()           # (t, n)

    def add(self, t, n=1):
        if n:
            self.events.append((t, n))

    def per_min(self, t):
        while self.events and self.events[0][0] < t - self.window:
            self.events.popleft()
        return sum(n for _, n in self.events) / (self.window / 60)

    def reset(self):
        self.events.clear()
