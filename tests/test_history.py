"""/api/history 의 step 묶음 — 고배속 mock 의 수천 행이 휴대폰에서 히어로를 비우던 문제의 회귀 방지."""
from app.routers.history import bucket


def rows(n, start="2026-09-03T12:00:00", every=0.5):
    import datetime as dt
    t0 = dt.datetime.fromisoformat(start)
    return [{"ts": (t0 + dt.timedelta(seconds=i * every)).isoformat(timespec="milliseconds"), "queue_len": i % 10,
             "rate_per_min": 12.0, "wait_min": None if i % 7 == 0 else float(i % 5), "state": "ok" if i % 20 else "insufficient_rate"}
            for i in range(n)]


def test_10초_묶음은_행_수를_20분의_1로():
    r = rows(3600)                                   # 0.5초 간격 30분 = 3,600행
    b = bucket(r, 10)
    assert len(b) == 180 and b[0]["ts"] == r[0]["ts"] and b[0]["n"] == 20
    assert all(x["wait_min"] is None or 0 <= x["wait_min"] <= 4 for x in b)
    assert sum(x["n"] for x in b) == 3600


def test_state_는_묶음의_마지막_표본():
    r = rows(40)
    b = bucket(r, 10)                                # 0~19 → 첫 묶음(마지막 i=19: ok), 20~39 → 둘째(마지막 i=39: ok)
    assert [x["state"] for x in b] == ["ok", "ok"]
    r[19]["state"] = "no_data"
    assert bucket(r, 10)[0]["state"] == "no_data"


def test_step_0_은_원본_그대로_빈_입력은_빈_출력():
    r = rows(5)
    assert bucket(r, 0) == r and bucket([], 10) == []


def test_묶음_안_평균():
    r = [{"ts": "2026-09-03T12:00:00.000", "queue_len": 10, "rate_per_min": 10.0, "wait_min": 1.0, "state": "ok"},
         {"ts": "2026-09-03T12:00:04.000", "queue_len": 20, "rate_per_min": 20.0, "wait_min": 3.0, "state": "ok"},
         {"ts": "2026-09-03T12:00:11.000", "queue_len": 30, "rate_per_min": 30.0, "wait_min": None, "state": "stale"}]
    b = bucket(r, 10)
    assert b[0] == {"ts": r[0]["ts"], "queue_len": 15, "rate_per_min": 15.0, "wait_min": 2.0, "state": "ok", "n": 2}
    assert b[1]["wait_min"] is None and b[1]["state"] == "stale" and b[1]["n"] == 1
