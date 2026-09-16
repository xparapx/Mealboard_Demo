import datetime as dt
from fastapi import APIRouter
from ..config import FEED_SOURCE, STALE_SEC          # STALE_SEC: 이 시간 넘게 새 행이 없으면 '데이터 없음'으로 본다
from ..db import connect
from ..lunch import describe, meal_next, meal_now, next_meal_day
from ..mealjson import read_meal

router = APIRouter()
WD = "월화수목금토일"


def next_with_day(now):
    """다음 창 + 그 창이 실제로 열리는 급식 날(주말·공휴일 건너뜀). 오늘 남은 창이 있어도 오늘이 급식 없는 날이면 다음 급식 날의 첫 창.
    → dict(label, lo, hi, days, date, weekday) 또는 None"""
    nxt = meal_next(now)
    if not nxt:
        return None
    win, days = nxt
    dates = [d.get("date", "") for d in (read_meal().get("week") or []) if d.get("menu")]
    if days == 0:                                          # 오늘 안에 다음 창이 있다 — 오늘이 급식 있는 날일 때만 그대로
        nd = next_meal_day(now, dates)
        if nd and nd[1] == 0:
            d, k = nd
        else:
            nd = next_meal_day(now + dt.timedelta(days=1), dates)
            if not nd:
                return None
            d, k = nd[0], nd[1] + 1
            win = meal_next(now.replace(hour=0, minute=0))[0]    # 그날의 첫 창
    else:
        nd = next_meal_day(now + dt.timedelta(days=1), dates)
        if not nd:
            return None
        d, k = nd[0], nd[1] + 1
    out = describe(win)
    out.update({"days": k, "date": d.isoformat(), "weekday": WD[d.weekday()]})
    return out


def feed(now, state, source=FEED_SOURCE):
    """'지금 값이 실측인가' — 화면 맨 위 안내 띠가 읽는다(09-04). live 는 셋이 모두 맞을 때만:
    출처가 vision(카메라 노드) · 지금이 수집 창(3학년 점심·1·2학년 점심·석식) 안 · 표본이 끊기지 않음. now 는 열린 창, next 는 다음 창(며칠 뒤 days), meal_day 는 오늘이 급식 있는 날인지(NEIS 캐시 기준 — 시작 화면·자동 전환이 본다).
    창 밖에는 카메라 노드가 아무 행도 쓰지 않으므로(09-11) state 는 120초 뒤 no_data 가 된다 — 화면은 source·now 로 '급식 시간이 아닙니다' 와 '표본 끊김' 을 가른다"""
    w = meal_now(now)
    ymd = now.strftime("%Y%m%d")
    meal_day = any(d.get("date") == ymd and d.get("menu") for d in (read_meal().get("week") or []))
    return {"source": source, "live": source == "vision" and w is not None and state != "no_data",
            "now": describe(w), "next": next_with_day(now), "meal_day": meal_day}


def wait_range(con, now, win):
    """지금 열린 수집 창 안 '공표 대기(wait_min)'의 오늘 최소~최대(09-16 사용자 결정) — 화면 판정(여유·보통·혼잡)이
    고정 임계값 대신 이 범위 안 상대 위치를 쓴다. 창 밖이거나 표본이 모자라면 None(화면은 고정 기준으로 폴백)"""
    if win is None:
        return None
    day = now.strftime("%Y-%m-%d")
    lo_ts = f"{day}T{win.lo // 60:02d}:{win.lo % 60:02d}"
    row = con.execute("SELECT MIN(wait_min) lo, MAX(wait_min) hi, COUNT(wait_min) n FROM samples "
                      "WHERE ts >= ? AND wait_min IS NOT NULL AND state = 'ok'", (lo_ts,)).fetchone()
    if not row or row["n"] < 30 or row["lo"] is None:           # 30표본(약 5분)은 쌓여야 범위가 뜻을 가진다
        return None
    return {"lo": round(row["lo"], 1), "hi": round(row["hi"], 1), "n": row["n"]}


@router.get("/api/status")
def status():
    now = dt.datetime.now()
    con = connect()
    row = con.execute("SELECT * FROM samples ORDER BY ts DESC LIMIT 1").fetchone()
    rng = wait_range(con, now, meal_now(now))
    con.close()
    if row is None:
        return {"state": "no_data", "updated_at": None,
                "queue_len": None, "rate_per_min": None, "wait_min": None, "feed": feed(now, "no_data")}
    age = (now - dt.datetime.fromisoformat(row["ts"])).total_seconds()
    state = "no_data" if age > STALE_SEC else row["state"]
    return {"state": state, "updated_at": row["ts"], "stale": age > STALE_SEC,
            "queue_len": row["queue_len"], "rate_per_min": row["rate_per_min"],
            "wait_min": row["wait_min"],
            "wait_raw_min": row["wait_raw_min"], "measured_wait_min": row["measured_wait_min"], "calib": row["calib"],
            "wait_range": rng, "feed": feed(now, state)}
