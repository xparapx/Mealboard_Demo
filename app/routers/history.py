"""최근 N분의 대기 이력. 추이 그래프(대기시간 카드)가 30초마다 받는다.

표본은 vision 이 초당 한 번 안팎, mock(고배속)은 초당 세 번까지 쌓이므로 30분이면 수천 행·수백 KB 가 된다 — 휴대폰 회선에서 히어로가
몇 초씩 비는 원인이었다. 그래서 `step` 초 단위로 묶어 돌려준다(기본 10초 → 30분에 최대 180행). 묶음 안에서 queue·rate·wait 는 평균,
ts 는 첫 표본, state 는 마지막 표본(끊김·산출 불가가 마지막이면 그대로 드러난다). step=0 이면 원본 그대로."""
import datetime as dt

from fastapi import APIRouter, Query

from ..db import connect

router = APIRouter()
STEP_DEFAULT, STEP_MAX = 10, 300


def _epoch(ts):
    return dt.datetime.fromisoformat(ts).timestamp()


def bucket(rows, step):
    """[{ts, queue_len, rate_per_min, wait_min, state}] → step 초 단위 평균. 순수 함수(테스트 대상). step<=0 이면 그대로"""
    if step <= 0 or not rows:
        return list(rows)
    out, cur, key = [], [], None
    for r in rows:
        k = int(_epoch(r["ts"]) // step)
        if key is not None and k != key:
            out.append(_fold(cur))
            cur = []
        key = k
        cur.append(r)
    if cur:
        out.append(_fold(cur))
    return out


def _fold(rs):
    waits = [r["wait_min"] for r in rs if r["wait_min"] is not None]
    return {"ts": rs[0]["ts"],
            "queue_len": round(sum(r["queue_len"] or 0 for r in rs) / len(rs)),
            "rate_per_min": round(sum(r["rate_per_min"] or 0 for r in rs) / len(rs), 2),
            "wait_min": round(sum(waits) / len(waits), 1) if waits else None,
            "state": rs[-1]["state"], "n": len(rs)}


@router.get("/api/history")
def history(minutes: int = Query(120, ge=1, le=1440), step: int = Query(STEP_DEFAULT, ge=0, le=STEP_MAX)):
    since = (dt.datetime.now() - dt.timedelta(minutes=minutes)).isoformat(timespec="seconds")
    con = connect()
    rows = con.execute(
        "SELECT ts, queue_len, rate_per_min, wait_min, state "
        "FROM samples WHERE ts >= ? ORDER BY ts", (since,)).fetchall()
    con.close()
    return {"minutes": minutes, "step": step, "rows": bucket([dict(r) for r in rows], step)}
