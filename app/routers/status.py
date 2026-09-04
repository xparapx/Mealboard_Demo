import datetime as dt
from fastapi import APIRouter
from ..config import FEED_SOURCE, STALE_SEC          # STALE_SEC: 이 시간 넘게 새 행이 없으면 '데이터 없음'으로 본다
from ..db import connect
from ..lunch import describe, meal_next, meal_now

router = APIRouter()


def feed(now, state, source=FEED_SOURCE):
    """'지금 값이 실측인가' — 화면의 더미데이터 띠가 읽는다(09-04). live 는 셋이 모두 맞을 때만:
    출처가 vision(카메라 노드) · 지금이 수집 창(3학년 점심·1·2학년 점심·석식) 안 · 표본이 끊기지 않음. now 는 열린 창, next 는 다음 창(며칠 뒤 days)"""
    w = meal_now(now)
    nxt = meal_next(now)
    nxt_d = None
    if nxt:
        nxt_d = describe(nxt[0])
        nxt_d["days"] = nxt[1]
    return {"source": source, "live": source == "vision" and w is not None and state != "no_data",
            "now": describe(w), "next": nxt_d}


@router.get("/api/status")
def status():
    con = connect()
    row = con.execute("SELECT * FROM samples ORDER BY ts DESC LIMIT 1").fetchone()
    con.close()
    now = dt.datetime.now()
    if row is None:
        return {"state": "no_data", "updated_at": None,
                "queue_len": None, "rate_per_min": None, "wait_min": None, "feed": feed(now, "no_data")}
    age = (now - dt.datetime.fromisoformat(row["ts"])).total_seconds()
    state = "no_data" if age > STALE_SEC else row["state"]
    return {"state": state, "updated_at": row["ts"], "stale": age > STALE_SEC,
            "queue_len": row["queue_len"], "rate_per_min": row["rate_per_min"],
            "wait_min": row["wait_min"], "feed": feed(now, state)}
