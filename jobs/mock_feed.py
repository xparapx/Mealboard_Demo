"""vision/counter.py 의 대역.
점심시간 인파 곡선을 흉내내어 samples 테이블에 쓰고, 같은 틱의 위치를 data/zones.json 구역으로 세어
zone_samples 에 인원수만 남긴다(같은 트랜잭션). 구역 정의는 시작할 때 한 번 읽는다(바뀌면 재시작). 읽지 못하면 구역 인원수만 빠진다.
실제 vision 과 동시에 켜지 말 것 — SQLite 쓰기 주체는 항상 하나.

수집 시간창(09-04 운영 규칙, .env MEAL_WINDOWS): 창이 열리는 순간 곡선을 처음부터(줄 0명) 시작해 그 창의 인파를 흉내내고,
창 밖에서는 같은 곡선을 '더미' 로 계속 쓴다 — 화면은 /api/status feed 로 "지금은 더미데이터" 띠를 띄운다.
카메라 노드(vision, 로드맵 ④)는 창 밖에서 추론을 멈추고 여기의 Simulator 를 빌려 같은 더미를 쓴다.

실행:  uv run python -m jobs.mock_feed --speed 30
       --scenario stall : 45~55분 배식 중단 (insufficient_rate 상태 확인용)
       --scenario gap   : 80~90분 데이터 끊김 (no_data 상태 확인용)
       --meta           : 합성 프레임 메타데이터(META_FPS/초)를 관리 앱 소켓에 던진다 (vision/meta.py, PLAN §4.4 프레임 이벤트 스키마).
                          구독자가 없으면 sendto 가 실패할 뿐 — 어디에도 남지 않는다
"""
import argparse
import datetime as dt
import math
import random
import time
from collections import deque

from app.config import ZONES_JSON
from app.db import connect
from app.lunch import MEALS, meal_now
from vision.meta import MetaSender
from vision.record import write_sample
from vision.waittime import estimate_wait
from vision.zones import count_by_zone, load_zones, zone_of

TICK = 10           # 시뮬레이션 1틱 = 10초
META_FPS = 5        # --meta 프레임 발행 속도 (vision 디버그 계약과 같은 ≤5fps)
IMG_W, IMG_H = 1280, 720
ROI_Y = 0.10        # 바닥 y < ROI_Y 를 배식대 앞 ROI 로 본다 (템플릿 zones.json 의 counter 구역과 같은 띠)
CAPACITY = 20.0     # 배식대 처리 능력 (명/분)
CYCLE_MIN = 170     # 11:20 ~ 14:10 을 한 사이클로 보고 반복
# 실측 좌표계(x=폭 15.55m, y=배식구 벽→출입문 24.65m 의 0~1 정규화, static 탑뷰·zones.json 과 공유):
# 입구는 통로 끝단(출입문 벽의 창가 쪽) — 문 → 창가 통로 직진 → 배식구 벽(y=0)의 배식대 앞
PATH = [(0.08, 0.97), (0.05, 0.30), (0.10, 0.07), (0.55, 0.05)]


def arrival_rate(m):
    """경과 분 m → 도착률(명/분). 학년별 시간차 배식을 흉내낸 두 봉우리"""
    return 25 * math.exp(-((m - 25) / 12) ** 2) + 18 * math.exp(-((m - 70) / 15) ** 2)


def layout_points(n):
    """폴리라인 PATH 를 따라 n 명을 등간격 배치 + 지터 ±0.02. 좌표뿐, 사람을 식별할 정보는 없다"""
    seg = [math.dist(PATH[i], PATH[i + 1]) for i in range(len(PATH) - 1)]
    total = sum(seg)
    pts = []
    for i in range(n):
        d = (i + 0.5) / n * total
        k = 0
        while k < len(seg) - 1 and d > seg[k]:
            d -= seg[k]
            k += 1
        t = d / seg[k]
        x = PATH[k][0] + (PATH[k + 1][0] - PATH[k][0]) * t + random.uniform(-0.02, 0.02)
        y = PATH[k][1] + (PATH[k + 1][1] - PATH[k][1]) * t + random.uniform(-0.02, 0.02)
        pts.append({"x": round(min(max(x, 0), 1), 3), "y": round(min(max(y, 0), 1), 3)})
    return pts


def noisy(mu):
    """평균 mu 근처의 정수 난수 (음수 방지)"""
    return max(0, round(random.gauss(mu, max(mu, 1) ** 0.5)))


class Simulator:
    """더미 인파 곡선 하나. step() 마다 TICK 초를 진행하고 그 순간의 줄·처리율·대기·위치를 돌려준다(DB·파일·시계를 모른다).
    reset() 은 창이 열리는 순간 줄을 0 에서 다시 시작하려고 mock 이 부른다. 카메라 노드도 창 밖에서 같은 것을 빌려 쓴다"""

    def __init__(self, scenario="normal"):
        self.scenario = scenario
        self.reset()

    def reset(self):
        self.sim, self.queue = 0.0, 0
        self.served_log = deque()        # (sim_sec, 처리 인원) — 5분 이동평균 계산용

    def step(self):
        m = self.sim / 60
        cap = 0 if (self.scenario == "stall" and 45 <= m < 55) else CAPACITY
        self.queue += noisy(arrival_rate(m) * TICK / 60)          # 줄에 합류
        served = min(self.queue, noisy(cap * TICK / 60))          # 배식대 통과
        self.queue -= served
        self.served_log.append((self.sim, served))
        while self.served_log and self.served_log[0][0] < self.sim - 300:    # 최근 5분만 유지
            self.served_log.popleft()
        rate = sum(n for _, n in self.served_log) / 5.0            # λ (명/분)
        wait, state = estimate_wait(self.queue, rate)              # W = L / λ
        gap = self.scenario == "gap" and 80 <= m < 90
        out = {"m": m, "queue": self.queue, "served": served, "rate": round(rate, 2), "wait": wait, "state": state,
               "gap": gap, "pts": [] if gap else layout_points(self.queue)}
        self.sim += TICK
        if self.sim >= CYCLE_MIN * 60:                             # 한 사이클 끝 → 처음부터
            self.reset()
        return out


def to_image(x, y):
    """바닥 정규화 → 가짜 카메라 이미지 정규화. 배식구 벽 위에서 출입문 쪽을 내려다보는 카메라를 흉내낸다:
    가까울수록(y 작을수록) 화면 아래·크게, 멀수록 원근으로 가운데로 몬다. 호모그래피 대신 쓰는 합성 투영일 뿐이다"""
    depth = 1 - y
    v = 0.12 + 0.83 * depth
    u = 0.5 + (x - 0.5) * (0.45 + 0.55 * depth)
    return round(min(max(u, 0), 1), 3), round(min(max(v, 0), 1), 3)


def frame_event(frame_id, ts, pts, zones, rate, wait, state, crossings=()):
    """PLAN §4.4 프레임 이벤트 한 개. 입력은 익명 좌표뿐 — 사람을 식별할 정보는 만들 수도 없다"""
    tracks = []
    for i, p in enumerate(pts):
        u, v = to_image(p["x"], p["y"])
        h = 0.06 + 0.24 * v
        w = h * 0.42
        tracks.append({"id": 1000 + i, "bbox_norm": [round(max(u - w / 2, 0), 3), round(max(v - h, 0), 3), round(min(u + w / 2, 1), 3), v],
                       "foot_xy_norm": [u, v], "floor_xy_norm": [p["x"], p["y"]],
                       "in_roi": p["y"] < ROI_Y, "zone": zone_of(p["x"], p["y"], zones)})
    return {"frame_id": frame_id, "ts": ts, "fps": META_FPS, "infer_ms": round(random.gauss(118, 6), 1),
            "img_w": IMG_W, "img_h": IMG_H, "source": "mock", "model": "mock",
            "tracks": tracks, "crossings": list(crossings), "zone_counts": count_by_zone(pts, zones),
            "roi_count": sum(1 for t in tracks if t["in_roi"]), "rate_per_min": round(rate, 2), "wait_min": wait, "state": state}


def jitter(pts, d=0.004):
    """프레임 사이의 미세한 흔들림 — 같은 틱 안에서 점이 살아 있어 보이게"""
    return [{"x": round(min(max(p["x"] + random.uniform(-d, d), 0), 1), 3), "y": round(min(max(p["y"] + random.uniform(-d, d), 0), 1), 3)} for p in pts]


def hhmm(minute):
    return f"{minute // 60:02d}:{minute % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=30, help="실제 1초당 시뮬레이션 초")
    ap.add_argument("--scenario", choices=["normal", "stall", "gap"], default="normal")
    ap.add_argument("--meta", action="store_true", help="합성 프레임 메타데이터를 관리 앱 소켓에 발행")
    a = ap.parse_args()

    con = connect()
    sender = MetaSender() if a.meta else None
    frame_id = 0
    try:
        zones = load_zones(ZONES_JSON)["zones"]               # 템플릿 + zones.local.json overlay
    except (OSError, ValueError) as e:                        # 구역 정의가 깨져도 대기시간 피드는 멈추지 않는다 — 구역 인원수만 빠진다
        print(f"구역 정의를 읽지 못했다 - 구역 인원수 없이 계속한다: {e}")
        zones = []
    sim = Simulator(a.scenario)
    win = None                                                # 지금 열린 수집 창 — 바뀌는 순간 곡선을 처음부터
    windows = ", ".join(f"{w.label} {hhmm(w.lo)}~{hhmm(w.hi)}" for w in MEALS) or "없음"
    print(f"mock_feed 시작  speed={a.speed}  scenario={a.scenario}  zones={[z['id'] for z in zones]}  수집 창: {windows}")

    while True:
        cur = meal_now(dt.datetime.now())
        if cur != win:                                        # 창이 열리거나 닫힘 → 줄 0 명에서 다시(창 시작에 인파가 몰려드는 모양)
            win = cur
            sim.reset()
            print("--- " + (f"수집 창 열림: {win.label}" if win else "수집 창 닫힘 - 더미 곡선") + " ---")
        r = sim.step()
        counts, live = {}, not r["gap"]
        if live:
            ts = dt.datetime.now().isoformat(timespec="milliseconds")
            counts = write_sample(con, ts, r, zones)                  # vision/record.py — 카메라 노드와 같은 기록 함수
        zone_txt = " ".join(f"{z}={n}" for z, n in counts.items())
        tag = win.label if win else "더미"
        print(f"[{tag}] {r['m']:6.1f}분  대기 {r['queue']:3d}명  처리 {r['rate']:5.1f}/분  예상 {r['wait']}분  {r['state']}  {zone_txt}")

        pause = TICK / a.speed
        if sender is None or not live:
            time.sleep(pause)
            continue
        n = max(1, round(pause * META_FPS))                   # 이 틱 동안 보낼 프레임 수 (speed 30 → 0.33초에 2프레임)
        crossings = [{"id": 1000 + k, "dir": "out", "ts": ts} for k in range(r["served"])]
        for k in range(n):
            frame_id += 1
            ev = frame_event(frame_id, dt.datetime.now().isoformat(timespec="milliseconds"), jitter(r["pts"]), zones,
                             r["rate"], r["wait"], r["state"], crossings if k == 0 else ())
            sender.send(ev)
            time.sleep(pause / n)


if __name__ == "__main__":
    main()
