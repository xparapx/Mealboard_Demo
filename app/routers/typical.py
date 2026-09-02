"""평소 대기 곡선. 오늘 추이 뒤에 겹쳐 '지금이 평소보다 붐비는가'를 답한다.

기준은 두 단계로 물러선다 —
  weekday : 같은 요일 최근 N주 (학기 중 시간표가 요일마다 다르므로 이게 본래 기준)
  recent  : 표본이 모자라면 요일을 묻지 않고 최근 7일
어느 쪽을 썼는지 `basis` 로 알려주고, 프론트는 범례 문구를 거기에 맞춘다.
오늘 데이터는 언제나 제외한다 (비교 대상이 자기 자신이 되면 안 된다).
"""
import datetime as dt
from fastapi import APIRouter, Query
from ..db import connect
from ..lunch import BUCKET_MIN          # 5분 구간 — 집계(rollup)와 같은 눈금

router = APIRouter()

MIN_BUCKETS = 6       # 이보다 적게 모이면 그 기준은 쓸모없다고 보고 다음 단계로


def window(now, minutes):
    """[now-minutes, now] 를 '자정부터 몇 분' 범위로. 자정을 넘어가면 0 으로 자른다(급식은 한낮)."""
    end = now.hour * 60 + now.minute
    return max(0, end - minutes), end


def _rows(con, since, before, lo, hi, weekday):
    mod = "(CAST(strftime('%H', ts) AS INTEGER) * 60 + CAST(strftime('%M', ts) AS INTEGER))"
    sql = (f"SELECT {mod} / ? AS b, AVG(wait_min) AS w, COUNT(*) AS n, COUNT(DISTINCT date(ts)) AS d "
           f"FROM samples WHERE wait_min IS NOT NULL AND ts >= ? AND ts < ? AND {mod} BETWEEN ? AND ?")
    args = [BUCKET_MIN, since, before, lo, hi]
    if weekday is not None:
        sql += " AND CAST(strftime('%w', ts) AS INTEGER) = ?"
        args.append(weekday)
    return con.execute(sql + " GROUP BY b ORDER BY b", args).fetchall()


@router.get("/api/typical")
def typical(minutes: int = Query(120, ge=10, le=1440), weeks: int = Query(2, ge=1, le=8)):
    now = dt.datetime.now()
    lo, hi = window(now, minutes)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    before = today.isoformat(timespec="seconds")

    con = connect()
    wd = int(now.strftime("%w"))                 # SQLite strftime('%w') 와 같은 규칙 (0=일요일)
    plans = [("weekday", (today - dt.timedelta(weeks=weeks)).isoformat(timespec="seconds"), wd),
             ("recent", (today - dt.timedelta(days=7)).isoformat(timespec="seconds"), None)]
    for basis, since, weekday in plans:
        rows = _rows(con, since, before, lo, hi, weekday)
        if len(rows) >= MIN_BUCKETS:
            con.close()
            return {"state": "ok", "basis": basis, "bucket_min": BUCKET_MIN,
                    "days": max(r["d"] for r in rows),
                    "rows": [{"minute_of_day": r["b"] * BUCKET_MIN,
                              "wait_min": round(r["w"], 1), "n": r["n"]} for r in rows]}
    con.close()
    return {"state": "no_data", "basis": None, "bucket_min": BUCKET_MIN, "days": 0, "rows": []}
