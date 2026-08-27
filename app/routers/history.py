import datetime as dt
from fastapi import APIRouter, Query
from ..db import connect

router = APIRouter()


@router.get("/api/history")
def history(minutes: int = Query(120, ge=1, le=1440)):
    since = (dt.datetime.now() - dt.timedelta(minutes=minutes)).isoformat(timespec="seconds")
    con = connect()
    rows = con.execute(
        "SELECT ts, queue_len, rate_per_min, wait_min, state "
        "FROM samples WHERE ts >= ? ORDER BY ts", (since,)).fetchall()
    con.close()
    return {"minutes": minutes, "rows": [dict(r) for r in rows]}
