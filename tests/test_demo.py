"""심사위원 구동 경로(jobs/demo.py, 10-18 N3) — 순수 모델이 결정론적이고 그럴 법한 범위인지, 생성 폴더가 운영 data/ 와 분리되는지.
전체 생성(generate)은 환경 변수로 app.config 를 바꾸므로 별도 프로세스에서만 돈다(아래 subprocess 검사 1건)"""
import datetime as dt
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from jobs import demo

ROOT = Path(__file__).resolve().parent.parent
ANCHOR = dt.datetime.fromisoformat(demo.ANCHOR)
TODAY = ANCHOR.date()


def test_학교_날짜는_평일만_공휴일_빼고_기준일까지():
    days = demo.school_days(TODAY)
    assert days[-1] == TODAY and days[0].weekday() == 0 and all(d.weekday() < 5 for d in days)
    assert dt.date(2026, 9, 24) not in days and dt.date(2026, 10, 9) not in days      # 추석·한글날
    assert 30 <= len(days) <= 40


def test_창_모델은_결정론적이고_값이_그럴_법하다():
    days = set(demo.school_days(TODAY))
    waves = demo.waves_for(TODAY, days, TODAY)
    lo, hi, n, mu, kind, f = waves[1]                                      # 1·2학년 점심 12:30~13:40
    a = demo.simulate_wave(TODAY, lo, hi, n, mu, kind, f, TODAY, with_points=False)
    b = demo.simulate_wave(TODAY, lo, hi, n, mu, kind, f, TODAY, with_points=False)
    assert a == b                                                          # 같은 씨앗 → 같은 틱(누가 켜도 같은 화면)
    assert a[0]["sec"] == lo * 60 and a[-1]["sec"] < hi * 60 and all(t["sec"] % demo.TICK == 0 for t in a)
    waits = [t["wait"] for t in a if t["wait"] is not None]
    assert 3 <= max(waits) <= 12                                           # 피크 대기는 몇 분 — 수십 분이면 모델이 틀렸다
    assert max(t["queue"] for t in a) <= 90 and all(t["state"] in ("ok", "insufficient_rate") for t in a)
    assert all(t["rate"] >= 0 and t["served_n"] >= 0 for t in a)


def test_오늘_3학년_창에는_병목_구간이_있다():
    assert demo.bottleneck_for(TODAY, *demo.LUNCH_WAVES[0][:2], "lunch", TODAY) == (11 * 60 + 30, 11 * 60 + 35)
    assert demo.bottleneck_for(TODAY, 17 * 60 + 30, 18 * 60 + 30, "dinner", TODAY) is None


def test_휴일_전날은_석식이_30분_앞이다():
    days = set(demo.school_days(TODAY))
    thu = dt.date(2026, 9, 23)                                             # 추석 연휴 전날(수)
    assert demo.waves_for(thu, days)[-1][0] == 17 * 60
    assert demo.waves_for(dt.date(2026, 10, 13), days)[-1][0] == 17 * 60 + 30


def test_위치는_정규화_좌표만():
    import random
    pts = demo._points(random.Random(1), 12, 30)
    assert len(pts) == 42 and all(set(p) == {"x", "y"} and 0 <= p["x"] <= 1 and 0 <= p["y"] <= 1 for p in pts)
    from vision.zones import point_in_polygon
    assert all(point_in_polygon(p["x"], p["y"], demo.CAMERA_VIEW) or p["x"] <= 0.12 for p in pts)   # 10-19: 카메라 가시 영역 안(줄은 오른쪽 통로)
    assert not any(p["x"] > 0.65 for p in pts)                                                      # 왼쪽 열(0.72)·출구쪽은 화각 밖


def test_생성은_운영_data_폴더를_거부한다():
    with pytest.raises(SystemExit):
        demo.main(["--data", "data", "--generate-only"])


@pytest.mark.slow
def test_전체_생성은_별도_폴더에_여섯_화면_재료를_만든다(tmp_path):
    out = tmp_path / "demo"
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "jobs.demo", "--generate-only", "--data", str(out)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    assert r.returncode == 0, r.stderr
    for name in ("queue.db", "insights.db", "reports.db", "meal.json", "news.json", "positions.json", "zones.json", "zones.local.json"):
        assert (out / name).exists(), name
    q = sqlite3.connect(out / "queue.db")
    last = q.execute("SELECT ts, state FROM samples ORDER BY ts DESC LIMIT 1").fetchone()
    assert last[0] < demo.ANCHOR and last[0] > "2026-10-14T12:43"          # 기준 시각 직전까지 — 그 뒤는 피더가 쓴다
    assert q.execute("SELECT COUNT(*) FROM cell_samples").fetchone()[0] > 1000
    i = sqlite3.connect(out / "insights.db")
    assert i.execute("SELECT COUNT(*) FROM lunch_days WHERE meal='lunch'").fetchone()[0] >= 30
    assert i.execute("SELECT COUNT(*) FROM events WHERE kind='bottleneck' AND date='2026-10-14'").fetchone()[0] == 1
    assert i.execute("SELECT value FROM meta WHERE key='source'").fetchone()[0] == "mock"
    rep = sqlite3.connect(out / "reports.db").execute("SELECT kind, for_date FROM reports ORDER BY kind").fetchall()
    assert ("preview", "2026-10-14") in rep and any(k == "recap" for k, _ in rep)
    meal = json.loads((out / "meal.json").read_text(encoding="utf-8"))
    assert meal["today"]["date"] == "20261014" and meal["today"]["menu"][0].startswith("등심돈가스")
    assert not (ROOT / "data" / "demo_test_marker").exists()               # 운영 data/ 에는 아무것도 쓰지 않았다(폴더가 tmp 였다)
