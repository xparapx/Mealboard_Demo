"""vision/counter.py 의 대역.
점심시간 인파 곡선을 흉내내어 samples 테이블에 쓴다.
실제 vision 과 동시에 켜지 말 것 — SQLite 쓰기 주체는 항상 하나.

실행:  uv run python -m jobs.mock_feed --speed 30
       --scenario stall : 45~55분 배식 중단 (insufficient_rate 상태 확인용)
       --scenario gap   : 80~90분 데이터 끊김 (no_data 상태 확인용)
"""
import argparse
import datetime as dt
import json
import math
import os
import random
import time
from collections import deque

from app.config import DATA
from app.db import connect
from vision.waittime import estimate_wait

TICK = 10           # 시뮬레이션 1틱 = 10초
CAPACITY = 20.0     # 배식대 처리 능력 (명/분)
CYCLE_MIN = 170     # 11:20 ~ 14:10 을 한 사이클로 보고 반복
PATH = [(0.10, 0.08), (0.07, 0.50), (0.09, 0.82), (0.45, 0.88)]   # 입구(좌상) → 좌측 통로 아래로 → 배식대 앞(하단 중앙) — 0~1 정규화
POSITIONS = DATA / "positions.json"


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


def write_positions(ts, queue):
    """data/positions.json 을 원자적으로 덮어쓴다 (tmp 에 쓰고 os.replace). 순간 상태만, 이력 없음.
    Windows 에서는 API 가 읽는 순간 os.replace 가 거부될 수 있어 잠깐 재시도하고, 끝내 안 되면 이번 틱은 건너뛴다(옛 파일 유지)."""
    tmp = POSITIONS.parent / (POSITIONS.name + ".tmp")
    tmp.write_text(json.dumps({"updated_at": ts, "n": queue, "points": layout_points(queue)}), encoding="utf-8")
    for _ in range(5):
        try:
            os.replace(tmp, POSITIONS)
            return
        except PermissionError:
            time.sleep(0.02)
    tmp.unlink(missing_ok=True)


def noisy(mu):
    """평균 mu 근처의 정수 난수 (음수 방지)"""
    return max(0, round(random.gauss(mu, max(mu, 1) ** 0.5)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=30, help="실제 1초당 시뮬레이션 초")
    ap.add_argument("--scenario", choices=["normal", "stall", "gap"], default="normal")
    a = ap.parse_args()

    con = connect()
    served_log = deque()        # (sim_sec, 처리 인원) — 5분 이동평균 계산용
    queue, sim = 0, 0.0
    print(f"mock_feed 시작  speed={a.speed}  scenario={a.scenario}")

    while True:
        m = sim / 60
        cap = 0 if (a.scenario == "stall" and 45 <= m < 55) else CAPACITY

        queue += noisy(arrival_rate(m) * TICK / 60)          # 줄에 합류
        served = min(queue, noisy(cap * TICK / 60))          # 배식대 통과
        queue -= served

        served_log.append((sim, served))
        while served_log and served_log[0][0] < sim - 300:    # 최근 5분만 유지
            served_log.popleft()
        rate = sum(n for _, n in served_log) / 5.0            # λ (명/분)
        wait, state = estimate_wait(queue, rate)              # W = L / λ

        if not (a.scenario == "gap" and 80 <= m < 90):
            ts = dt.datetime.now().isoformat(timespec="milliseconds")
            con.execute("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?)",
                        (ts, queue, round(rate, 2), wait, state))
            con.commit()
            write_positions(ts, queue)                        # 카메라(=mock) 가 멈추면 이 파일도 멈춘다 → API 가 stale 로 판단
        print(f"{m:6.1f}분  대기 {queue:3d}명  처리 {rate:5.1f}/분  예상 {wait}분  {state}")

        sim += TICK
        if sim >= CYCLE_MIN * 60:                             # 한 사이클 끝 → 처음부터
            sim, queue = 0.0, 0
            served_log.clear()
        time.sleep(TICK / a.speed)


if __name__ == "__main__":
    main()
