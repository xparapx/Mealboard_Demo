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

    def update(self, tid, p):
        d = signed_dist(self.a, self.b, p) * self.out_dir      # >0 = 출구 쪽
        if abs(d) < self.buffer:
            return 0                                            # 완충띠 — 판정을 미룬다(기억은 그대로)
        s = 1 if d > 0 else -1
        prev = self.side.get(tid)
        self.side[tid] = s
        if prev is None or prev == s:
            return 0
        return s

    def forget(self, alive):
        """사라진 트랙의 기억을 지운다(ByteTrack ID 는 재사용되지 않지만 dict 가 자라지 않게)"""
        alive = set(alive)
        for tid in [t for t in self.side if t not in alive]:
            del self.side[tid]

    def reset(self):
        self.side.clear()


class RateWindow:
    """통과 이벤트의 이동합 → 명/분. 기본 5분 창(CLAUDE.md §2 λ = 5분 이동평균). 시각은 단조 초"""

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
