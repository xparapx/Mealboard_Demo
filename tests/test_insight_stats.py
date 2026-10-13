"""통계 화면(10-13) — 시간대 분포(밴드)·육각 클러스터의 순수 계산과 /api/insight/stats·density_typical 의 응답 모양.
집계 DB 는 임시 파일에 rollup 의 SCHEMA 로 만든다(실제 insights.db 는 건드리지 않는다)."""
import sqlite3

import pytest

from app.insight_calc import band_stats, hex_clusters


def test_band_stats_는_bin_별_평균_표준편차_사분위():
    rows = [{"date": "2026-10-06", "bin": 720, "avg_wait": 1.0}, {"date": "2026-10-07", "bin": 720, "avg_wait": 3.0},
            {"date": "2026-10-08", "bin": 720, "avg_wait": 2.0}, {"date": "2026-10-06", "bin": 725, "avg_wait": 4.0},
            {"date": "2026-10-07", "bin": 725, "avg_wait": None}]
    b = band_stats(rows)
    assert [x["bin"] for x in b] == [720, 725]
    assert b[0]["n"] == 3 and b[0]["mean"] == 2.0 and b[0]["sd"] == 1.0 and b[0]["lo"] == 1.0 and b[0]["hi"] == 3.0
    assert b[0]["p25"] <= b[0]["mean"] <= b[0]["p75"]
    assert b[1] == {"bin": 725, "n": 1, "mean": 4.0, "sd": 0.0, "p25": 4.0, "p75": 4.0, "lo": 4.0, "hi": 4.0}   # 하루뿐이면 띠 폭 0
    assert band_stats([]) == []


def test_hex_clusters_는_이웃한_진한_타일을_묶는다():
    cols, rows = 10, 18
    # 두 덩어리: (row0: 0,1,2) 와 (row5: 54,55) — 서로 멀다. 옅은 타일(w<0.5)은 무시
    cells = [{"i": 0, "avg": 2.0, "w": 1.0}, {"i": 1, "avg": 1.5, "w": 0.75}, {"i": 2, "avg": 1.0, "w": 0.5},
             {"i": 54, "avg": 1.2, "w": 0.6}, {"i": 55, "avg": 1.2, "w": 0.6}, {"i": 100, "avg": 0.4, "w": 0.2}]
    g = hex_clusters(cells, cols, rows)
    assert [x["rank"] for x in g] == [1, 2]
    assert g[0]["cells"] == [0, 1, 2] and g[0]["avg"] == 4.5 and g[0]["peak_i"] == 0
    assert g[1]["cells"] == [54, 55] and g[1]["n_cells"] == 2
    assert 0 <= g[0]["x"] <= 1 and 0 <= g[0]["y"] <= 1 and g[0]["x"] < g[0]["x"] + 0.2    # 무게중심은 정규화 좌표
    assert g[0]["x"] < 0.2 and g[0]["y"] < 0.1                                             # 첫 행 왼쪽 위
    assert hex_clusters([], cols, rows) == []


def test_hex_clusters_홀수_행_이웃():
    """홀수 행은 반 칸 오른쪽 — 셀 10(행1, 열0)은 행0 의 0·1 과 이웃, 셀 20(행2, 열0)은 행1 의 10 과 이웃"""
    cells = [{"i": 0, "avg": 1, "w": 1}, {"i": 10, "avg": 1, "w": 1}, {"i": 20, "avg": 1, "w": 1}]
    g = hex_clusters(cells, 10, 18)
    assert len(g) == 1 and g[0]["cells"] == [0, 10, 20]


@pytest.fixture
def insights(tmp_path, monkeypatch):
    from jobs.rollup import SCHEMA
    from app.routers import insight
    path = tmp_path / "insights.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute("INSERT INTO meta VALUES ('window', 'lunch')")
    for date, wd, aw, pw, served in (("2026-10-06", 2, 1.5, 4.0, 300), ("2026-10-07", 3, 2.5, 6.0, 320), ("2026-10-13", 2, 2.0, 5.0, 310)):
        con.execute("INSERT INTO lunch_days (date, meal, weekday, window_lo, window_hi, source, avg_wait, peak_wait, peak_wait_ts, served_est, "
                    "coverage_pct, golden_min, bottleneck_min) VALUES (?, 'lunch', ?, 690, 820, 'vision', ?, ?, ?, ?, 90, 20, 5)",
                    (date, wd, aw, pw, f"{date}T12:40:00", served))
        for b, w in ((720, 1.0 + wd), (725, 2.0 + wd), (730, 3.0)):
            con.execute("INSERT INTO lunch_bins (date, meal, weekday, bin, n, avg_wait) VALUES (?, 'lunch', ?, ?, 10, ?)", (date, wd, b, w))
        con.execute("INSERT INTO events VALUES (?, 'lunch', 'golden', ?, ?, 6, 1.0, '')", (date, f"{date}T12:02:00", f"{date}T12:08:00"))
        con.execute("INSERT INTO events VALUES (?, 'lunch', 'bottleneck', ?, ?, 3, 0.2, '')", (date, f"{date}T12:41:00", f"{date}T12:44:00"))
    con.execute("INSERT INTO menu_stats VALUES ('lunch', '돈가스', 3, 5.5, 2.0, 12, 120, '2026-10-01', '2026-10-13')")
    con.execute("INSERT INTO menu_stats VALUES ('lunch', '된장국', 2, 2.5, 1.0, 6, 80, '2026-10-01', '2026-10-13')")
    con.execute("INSERT INTO menu_stats VALUES ('lunch', '한번만', 1, 9.0, 1.0, 6, 80, '2026-10-01', '2026-10-01')")
    con.commit(); con.close()

    def ro(p=None, table="lunch_days"):
        if p is not None:                                   # queue.db 요청(오늘 실황·K)은 없음으로
            return None
        c = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(insight, "connect_ro", ro)
    monkeypatch.setattr(insight, "FEED_SOURCE", "vision")
    monkeypatch.setattr(insight, "ROLLUP_WINDOW", "lunch")
    monkeypatch.setattr(insight, "_since", lambda weeks: "2026-10-01")
    monkeypatch.setattr(insight, "_today_cells", lambda meal: (2, [{"minute_of_day": 720, "wait_min": 1.4}, {"minute_of_day": 725, "wait_min": None}]))
    insight._CACHE.clear()
    return insight


def test_stats_응답_모양(insights):
    r = insights._stats(4, "lunch")
    assert r["state"] == "ok" and r["n_days"] == 3 and r["meal"] == "lunch"
    bands = {b["bin"]: b for b in r["bands"]}
    assert set(bands) == {720, 725, 730}
    assert bands[730]["sd"] == 0.0 and bands[720]["n"] == 3 and bands[720]["lo"] < bands[720]["mean"] < bands[720]["hi"]
    assert r["today"] == [{"bin": 720, "wait": 1.4}]                                  # None 은 뺀다
    wd = {w["weekday"]: w for w in r["weekdays"]}
    assert wd[2]["days"] == 2 and wd[2]["avg_wait"] == 1.8 and wd[3]["served"] == 320  # 화요일 두 날 평균 (1.5+2.0)/2
    assert [d["date"] for d in r["daily"]] == ["2026-10-06", "2026-10-07", "2026-10-13"] and r["daily"][0]["k"] is None
    ev = {e["bin"]: e for e in r["events"]}
    assert ev[720]["golden_min"] == 18 and ev[760]["bottleneck_min"] == 9             # 12:00 bin 황금 6×3, 12:40 bin 병목 3×3
    assert [m["menu"] for m in r["menus"]] == ["돈가스", "된장국"] and r["menu_base"] == 4.0   # 하루뿐인 메뉴 제외, 기준 = 중앙값


def test_stats_는_10분_캐시(insights):
    a = insights.stats(4, "lunch")
    assert a["state"] == "ok"
    key = ("stats", 4, "lunch")
    assert key in insights._CACHE and insights.stats(4, "lunch") is a


def test_stats_집계_없으면_no_data(insights, monkeypatch):
    monkeypatch.setattr(insights, "_since", lambda weeks: "2027-01-01")
    r = insights._stats(1, "lunch")
    assert r["state"] == "no_data" and r["bands"] == [] and r["weekdays"] == []


def test_density_typical_큐db_없으면_no_data(monkeypatch):
    from app.routers import insight
    monkeypatch.setattr(insight, "connect_ro", lambda *a, **k: None)
    r = insight._density_typical(7, "lunch")
    assert r["state"] == "no_data" and r["cells"] == [] and r["clusters"] == []
