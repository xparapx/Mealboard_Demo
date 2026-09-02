import datetime as dt
from fastapi import APIRouter
from ..config import STALE_SEC          # 이 시간 넘게 새 행이 없으면 '데이터 없음'으로 본다
from ..db import connect

router = APIRouter()


@router.get("/api/status")
def status():
    con = connect()
    row = con.execute("SELECT * FROM samples ORDER BY ts DESC LIMIT 1").fetchone()
    con.close()
    if row is None:
        return {"state": "no_data", "updated_at": None,
                "queue_len": None, "rate_per_min": None, "wait_min": None}
    age = (dt.datetime.now() - dt.datetime.fromisoformat(row["ts"])).total_seconds()
    state = "no_data" if age > STALE_SEC else row["state"]
    return {"state": state, "updated_at": row["ts"], "stale": age > STALE_SEC,
            "queue_len": row["queue_len"], "rate_per_min": row["rate_per_min"],
            "wait_min": row["wait_min"]}
