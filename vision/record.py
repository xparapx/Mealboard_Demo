"""queue.db 표본 기록 + positions.json — vision(counter) 과 mock 이 같은 함수로 쓴다(쓰기 주체는 그 순간 하나뿐, CLAUDE.md §2).
DB 에는 숫자만 간다: samples(줄·λ·대기·상태), zone_samples(구역별 인원수), cell_samples(육각 타일별 인원수).
positions.json 은 익명 바닥 좌표의 순간 상태 하나를 덮어쓸 뿐 이력이 없다. 바닥 좌표가 없으면(호모그래피 보정 전) 그 둘은 건너뛴다."""
import json
import os
import time

from app.config import DATA
from vision.zones import count_by_cell, count_by_zone

POSITIONS = DATA / "positions.json"


def write_positions(ts, queue, pts):
    """data/positions.json 을 원자적으로 덮어쓴다 (tmp 에 쓰고 os.replace). 순간 상태만, 이력 없음.
    Windows 에서는 API 가 읽는 순간 os.replace 가 거부될 수 있어 잠깐 재시도하고, 끝내 안 되면 이번 틱은 건너뛴다(옛 파일 유지)."""
    tmp = POSITIONS.parent / (POSITIONS.name + ".tmp")
    tmp.write_text(json.dumps({"updated_at": ts, "n": queue, "points": pts}), encoding="utf-8")
    for _ in range(5):
        try:
            os.replace(tmp, POSITIONS)
            return
        except PermissionError:
            time.sleep(0.02)
    tmp.unlink(missing_ok=True)


def write_sample(con, ts, s, zones):
    """s = {queue, rate, wait, state, pts} — pts 는 바닥 정규화 점 [{x,y}] 또는 None(좌표 없음).
    samples·zone_samples·cell_samples 를 한 트랜잭션으로(반쪽 표본이 남지 않게). 구역별 인원수를 돌려준다"""
    pts = s.get("pts")
    counts = count_by_zone(pts, zones) if pts is not None else {}
    con.execute("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?)", (ts, s["queue"], s["rate"], s["wait"], s["state"]))
    if pts is not None:
        con.executemany("INSERT OR REPLACE INTO zone_samples VALUES (?,?,?)", [(ts, z, n) for z, n in counts.items()])
        con.executemany("INSERT OR REPLACE INTO cell_samples VALUES (?,?,?)", [(ts, c, n) for c, n in count_by_cell(pts).items()])
    con.commit()
    if pts is not None:
        write_positions(ts, s["queue"], pts)        # 카메라(또는 mock) 가 멈추면 이 파일도 멈춘다 → API 가 stale 로 판단
    return counts
