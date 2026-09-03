"""인사이트 API 8종 — insights.db(집계) 와 reports.db(LLM 글) 를 읽기 전용으로 내준다.

공통 계약: `state: ok | no_data`, 무엇을 근거로 했는지 `basis` 동봉, insights.db 가 없으면 `no_data` + `reason` (파일을 만들지 않는다).
오늘은 집계가 아직 없을 수 있어(rollup 은 14:10) day·quality 는 queue.db 로 즉석 계산한다 — `basis: live`.
집계 행은 .env FEED_SOURCE(mock|vision) 와 같은 출처만 쓴다: 스테이징 mock 표본이 실측 히트맵에 섞이지 않게.
이 엔드포인트들은 30초 폴링 대상이 아니다(화면 진입 시 1회, day·quality 만 5분).
"""
import datetime as dt
import json
import statistics

from fastapi import APIRouter, Query

from ..config import FEED_SOURCE, MEAL_JSON, ROLLUP_WINDOW, ZONES_JSON
from ..db import connect as connect_queue
from ..insight_calc import coverage, day_summary, normalize_menu
from ..insights_db import connect_reports_ro, connect_ro
from ..lunch import BUCKET_MIN, bounds, seconds_of_day
from vision.zones import load_zones, polygon_area_m2

router = APIRouter(prefix="/api/insight")
DATE = r"^\d{4}-\d{2}-\d{2}$"
LIVE_MIN = 180                 # 오늘 즉석 계산에 쓰는 최근 분
GOLDEN_WAIT = 3.0
MENU_FACTOR = (0.7, 1.5)       # 예보 보정 클램프
NO_DB = "insights.db 가 아직 없다 — jobs/rollup.py 가 만든다"


def _no(reason, **extra):
    return {"state": "no_data", "reason": reason, **extra}


def _today():
    return dt.date.today().isoformat()


def _since(weeks):
    return (dt.date.today() - dt.timedelta(weeks=weeks)).isoformat()


def _weekday(date):
    return (dt.date.fromisoformat(date).weekday() + 1) % 7          # SQLite %w 규칙, 0=일요일


def _window():
    lo, hi = bounds(ROLLUP_WINDOW)
    return {"lo": lo, "hi": hi, "name": ROLLUP_WINDOW}


def _meal():
    if not MEAL_JSON.exists():
        return {}
    try:
        return json.loads(MEAL_JSON.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _menu_on(date):
    """meal.json 의 week[] 에서 그날 메뉴(정제된 이름). 없으면 []"""
    ymd = date.replace("-", "")
    for d in _meal().get("week") or []:
        if d.get("date") == ymd:
            return [m for m in (normalize_menu(x) for x in d.get("menu") or []) if m]
    return []


def _live_samples(minutes=LIVE_MIN):
    since = (dt.datetime.now() - dt.timedelta(minutes=minutes)).isoformat(timespec="seconds")
    con = connect_queue()
    rows = [dict(r) for r in con.execute(
        "SELECT ts, queue_len, rate_per_min, wait_min, state FROM samples WHERE ts >= ? ORDER BY ts", (since,))]
    con.close()
    return rows


def _live_summary(date):
    lo, hi = bounds(ROLLUP_WINDOW)
    now = dt.datetime.now()
    nmin = now.hour * 60 + now.minute
    return day_summary(_live_samples(), date, max(lo, nmin - LIVE_MIN), min(hi, nmin + 1), seconds_of_day(now))


def _rollup_meta(con):
    run = con.execute("SELECT finished_at FROM runs WHERE ok = 1 ORDER BY id DESC LIMIT 1").fetchone()
    return {"last_run": run["finished_at"] if run else None,
            "schema_version": con.execute("PRAGMA user_version").fetchone()[0]}


# ---- 1. 요일×시각 히트맵 -----------------------------------------------------------------

@router.get("/heatmap")
def heatmap(weeks: int = Query(4, ge=1, le=12)):
    con = connect_ro()
    if con is None:
        return _no(NO_DB, cells=[], window=_window())
    rows = con.execute(
        "SELECT b.weekday, b.bin, AVG(b.avg_wait) w, AVG(b.avg_queue) q, COUNT(DISTINCT b.date) d "
        "FROM lunch_bins b JOIN lunch_days l ON l.date = b.date "
        "WHERE l.source = ? AND b.date >= ? GROUP BY b.weekday, b.bin ORDER BY b.weekday, b.bin", (FEED_SOURCE, _since(weeks))).fetchall()
    days = con.execute("SELECT COUNT(*) FROM lunch_days WHERE source = ? AND date >= ?", (FEED_SOURCE, _since(weeks))).fetchone()[0]
    con.close()
    if not rows:
        return _no("집계된 날이 없다", cells=[], window=_window(), days=0)
    return {"state": "ok", "basis": "weekday" if days >= 5 else "recent", "weeks": weeks, "days": days,
            "bucket_min": BUCKET_MIN, "window": _window(), "source": FEED_SOURCE,
            "cells": [{"weekday": r["weekday"], "minute_of_day": r["bin"],
                       "wait_min": round(r["w"], 1) if r["w"] is not None else None,
                       "queue": round(r["q"], 1) if r["q"] is not None else None, "n_days": r["d"]} for r in rows]}


# ---- 2. 하루 -----------------------------------------------------------------------------

@router.get("/day")
def day(date: str | None = Query(None, pattern=DATE)):
    date = date or _today()
    con = connect_ro()
    row = con.execute("SELECT * FROM lunch_days WHERE date = ?", (date,)).fetchone() if con else None
    if row is None:
        if con:
            con.close()
        if date != _today():
            return _no(NO_DB if con is None else "그날의 집계가 없다", date=date)
        s = _live_summary(date)                               # 오늘: 집계 전이면 최근 180분을 즉석 계산
        summary = {k: v for k, v in s.items() if k not in ("golden", "bottlenecks", "events", "bins")}
        return {"state": "ok" if s["n_samples"] else "no_data", "basis": "live", "date": date, "summary": summary,
                "menu": _menu_on(date), "golden": s["golden"], "bottlenecks": s["bottlenecks"],
                "events": s["events"], "bins": s["bins"], **({} if s["n_samples"] else {"reason": "최근 표본이 없다"})}
    summary = dict(row)
    menu = json.loads(summary.pop("menu_json") or "[]")
    events = [dict(r) for r in con.execute("SELECT kind, start_ts, end_ts, minutes, value, detail FROM events WHERE date = ? ORDER BY start_ts", (date,))]
    bins = [dict(r) for r in con.execute("SELECT bin, n, ok_n, insufficient_n, avg_queue, max_queue, avg_rate, avg_wait, max_wait FROM lunch_bins WHERE date = ? ORDER BY bin", (date,))]
    con.close()
    return {"state": "ok", "basis": "rollup", "date": date, "summary": summary, "menu": menu,
            "golden": [e for e in events if e["kind"] == "golden"],
            "bottlenecks": [e for e in events if e["kind"] == "bottleneck"], "events": events, "bins": bins}


# ---- 3. 메뉴 인기 ---------------------------------------------------------------------------

@router.get("/menus")
def menus(n: int = Query(5, ge=1, le=20), min_days: int = Query(2, ge=1, le=30)):
    con = connect_ro()
    if con is None:
        return _no(NO_DB, items=[])
    rows = con.execute(
        "SELECT menu, n_days, popularity, avg_rise_rate, avg_peak_wait, last_date FROM menu_stats "
        "WHERE n_days >= ? AND popularity IS NOT NULL ORDER BY popularity DESC, n_days DESC LIMIT ?", (min_days, n)).fetchall()
    allrows = con.execute("SELECT avg_rise_rate, avg_peak_wait FROM menu_stats").fetchall()
    con.close()
    base = {k: (round(statistics.median(v), 2) if (v := [r[k] for r in allrows if r[k] is not None]) else None)
            for k in ("avg_rise_rate", "avg_peak_wait")}
    if not rows:
        return _no(f"{min_days}일 이상 나온 메뉴가 아직 없다", items=[], baseline=base)
    return {"state": "ok", "basis": "menu_stats", "min_days": min_days, "baseline": base, "items": [dict(r) for r in rows]}


# ---- 4. 예보 ----------------------------------------------------------------------------

def _typical_curve(con, weekday, weeks):
    """같은 요일 최근 N주 → 모자라면 최근 7일(요일 무관). (basis, [{minute_of_day, wait}])"""
    plans = [("weekday", "AND b.weekday = ? AND b.date >= ?", (weekday, _since(weeks))),
             ("recent", "AND b.date >= ?", ((dt.date.today() - dt.timedelta(days=7)).isoformat(),))]
    for basis, cond, args in plans:
        rows = con.execute(
            "SELECT b.bin, AVG(b.avg_wait) w FROM lunch_bins b JOIN lunch_days l ON l.date = b.date "
            f"WHERE l.source = ? AND b.avg_wait IS NOT NULL {cond} GROUP BY b.bin ORDER BY b.bin", (FEED_SOURCE, *args)).fetchall()
        if len(rows) >= 6:
            return basis, [{"minute_of_day": r["bin"], "wait": round(r["w"], 1)} for r in rows]
    return None, []


def _menu_factor(con, dishes):
    if not dishes:
        return 1.0, []
    marks = ",".join("?" * len(dishes))
    rows = con.execute(f"SELECT menu, popularity FROM menu_stats WHERE popularity IS NOT NULL AND menu IN ({marks})", dishes).fetchall()
    if not rows:
        return 1.0, []
    f = statistics.mean(r["popularity"] for r in rows) / 100
    return round(min(max(f, MENU_FACTOR[0]), MENU_FACTOR[1]), 2), [dict(r) for r in rows]


def _golden_from_curve(curve):
    out, cur = [], []
    for p in curve + [None]:
        if p and p["forecast_wait"] is not None and p["forecast_wait"] <= GOLDEN_WAIT and (not cur or p["minute_of_day"] - cur[-1]["minute_of_day"] == BUCKET_MIN):
            cur.append(p)
            continue
        if len(cur) * BUCKET_MIN >= 5:
            out.append({"start_min": cur[0]["minute_of_day"], "end_min": cur[-1]["minute_of_day"] + BUCKET_MIN})
        cur = [p] if p and p["forecast_wait"] is not None and p["forecast_wait"] <= GOLDEN_WAIT else []
    return out


@router.get("/forecast")
def forecast(date: str | None = Query(None, pattern=DATE), weeks: int = Query(4, ge=1, le=12)):
    if date is None:                                          # 급식이 끝난 뒤면 내일, 아니면 오늘
        now = dt.datetime.now()
        d = now.date() if now.hour * 60 + now.minute < bounds(ROLLUP_WINDOW)[1] else now.date() + dt.timedelta(days=1)
        date = d.isoformat()
    if dt.date.fromisoformat(date).weekday() >= 5:
        return {"state": "no_meal", "date": date, "reason": "주말에는 급식이 없다", "curve": [], "golden": []}
    con = connect_ro()
    if con is None:
        return _no(NO_DB, date=date, curve=[], golden=[])
    basis, typical = _typical_curve(con, _weekday(date), weeks)
    dishes = _menu_on(date)
    factor, matched = _menu_factor(con, dishes)
    con.close()
    if not typical:
        return _no("평소 곡선을 만들 집계가 아직 모자란다", date=date, curve=[], golden=[], menu=dishes)
    curve = [{"minute_of_day": p["minute_of_day"], "typical_wait": p["wait"], "forecast_wait": round(p["wait"] * factor, 1)} for p in typical]
    peak = max(curve, key=lambda p: p["forecast_wait"])
    return {"state": "ok", "basis": basis, "date": date, "weeks": weeks, "menu": dishes, "menu_factor": factor, "menu_matched": matched,
            "formula": f"forecast = typical({basis}) × menu_factor(인기 지수 평균/100, {MENU_FACTOR[0]}~{MENU_FACTOR[1]} 클램프)",
            "peak": {"minute_of_day": peak["minute_of_day"], "wait_min": peak["forecast_wait"]},
            "golden": _golden_from_curve(curve), "curve": curve}


# ---- 5. 측정 품질 --------------------------------------------------------------------------

@router.get("/quality")
def quality(date: str | None = Query(None, pattern=DATE)):
    date = date or _today()
    con = connect_ro()
    meta = _rollup_meta(con) if con else {"last_run": None, "schema_version": None}
    row = con.execute("SELECT * FROM lunch_days WHERE date = ?", (date,)).fetchone() if con else None
    if row is not None:
        gaps = [dict(r) for r in con.execute(
            "SELECT start_ts, end_ts, minutes FROM events WHERE date = ? AND kind = 'stale' ORDER BY start_ts", (date,))]
        con.close()
        return {"state": "ok", "basis": "rollup", "date": date, "coverage_pct": row["coverage_pct"], "stale_min": row["stale_min"],
                "insufficient_min": row["insufficient_min"], "n_samples": row["n_samples"], "gaps": gaps, "rollup": meta}
    if con:
        con.close()
    if date != _today():
        return _no(NO_DB if con is None else "그날의 집계가 없다", date=date, rollup=meta)
    lo, hi = bounds(ROLLUP_WINDOW)
    now = dt.datetime.now()
    s = _live_summary(date)
    cov = coverage([x for x in _live_samples(24 * 60) if x["ts"][:10] == date], date, lo, hi, seconds_of_day(now))
    return {"state": "ok" if s["n_samples"] else "no_data", "basis": "live", "date": date, "coverage_pct": cov["coverage_pct"],
            "stale_min": cov["stale_min"], "insufficient_min": s["insufficient_min"], "n_samples": s["n_samples"],
            "gaps": cov["gaps"], "rollup": meta, **({} if s["n_samples"] else {"reason": "최근 표본이 없다"})}


# ---- 6. 주간 영양 --------------------------------------------------------------------------

def _week_key(date):
    d = dt.date.fromisoformat(date)
    return (d - dt.timedelta(days=d.weekday())).isoformat()       # 그 주 월요일


def _weeks_from(days):
    """{date, kcal, energy_pct, mar, macro_ok, carb, protein, fat} 리스트 → 주별 평균"""
    weeks = {}
    for d in days:
        weeks.setdefault(_week_key(d["date"]), []).append(d)

    def avg(rows, k):
        v = [r[k] for r in rows if r.get(k) is not None]
        return round(sum(v) / len(v), 1) if v else None
    return [{"week": w, "days": len(rows), "kcal": avg(rows, "kcal"), "energy_pct": avg(rows, "energy_pct"), "mar": avg(rows, "mar"),
             "macro_ok_days": sum(1 for r in rows if r.get("macro_ok")),
             "carb_pct": avg(rows, "carb"), "protein_pct": avg(rows, "protein"), "fat_pct": avg(rows, "fat")}
            for w, rows in sorted(weeks.items())]


@router.get("/nutrition")
def nutrition(weeks: int = Query(8, ge=1, le=26)):
    con = connect_ro()
    if con is not None:
        rows = con.execute(
            "SELECT date, kcal, energy_pct, mar, macro_ok, carb_ratio carb, protein_ratio protein, fat_ratio fat "
            "FROM nutrition_days WHERE date >= ? ORDER BY date", (_since(weeks),)).fetchall()
        con.close()
        if rows:
            return {"state": "ok", "basis": "nutrition_days", "weeks": _weeks_from([dict(r) for r in rows])}
    week = []                                                 # 집계가 없으면 meal.json 의 이번 주만
    for d in _meal().get("week") or []:
        a = d.get("assess") or {}
        ratio = a.get("macro_ratio") or {}
        week.append({"date": f"{d['date'][:4]}-{d['date'][4:6]}-{d['date'][6:8]}", "kcal": d.get("kcal"),
                     "energy_pct": a.get("energy_pct"), "mar": a.get("mar"), "macro_ok": a.get("macro_ratio_ok"),
                     "carb": ratio.get("carb"), "protein": ratio.get("protein"), "fat": ratio.get("fat")})
    if not week:
        return _no("영양 이력도 이번 주 식단도 없다", weeks=[])
    return {"state": "ok", "basis": "meal_json", "weeks": _weeks_from(week)}


# ---- 7. 구역 점유율 --------------------------------------------------------------------------

@router.get("/zones")
def zones(weeks: int = Query(4, ge=1, le=12), date: str | None = Query(None, pattern=DATE)):
    try:
        doc = load_zones(ZONES_JSON)
    except (OSError, ValueError) as e:
        return _no(f"zones.json 문제: {e}", zones=[], bins=[])
    zlist = [{"id": z["id"], "label": z["name"], "area_m2": round(polygon_area_m2(z["polygon"], doc["floor"]), 1)} for z in doc["zones"]]
    con = connect_ro()
    if con is None:
        return _no(NO_DB, zones=zlist, bins=[])
    if date:
        rows = con.execute("SELECT z.bin, z.zone, z.avg_n FROM zone_bins z JOIN lunch_days l ON l.date = z.date "
                           "WHERE z.date = ? AND l.source = ? ORDER BY z.bin", (date, FEED_SOURCE)).fetchall()
        basis = "day"
    else:
        rows = con.execute("SELECT z.bin, z.zone, AVG(z.avg_n) avg_n FROM zone_bins z JOIN lunch_days l ON l.date = z.date "
                           "WHERE z.date >= ? AND l.source = ? GROUP BY z.bin, z.zone ORDER BY z.bin", (_since(weeks), FEED_SOURCE)).fetchall()
        basis = "recent"
    con.close()
    if not rows:
        return _no("구역 집계가 아직 없다", basis=basis, zones=zlist, bins=[])
    by_bin = {}
    for r in rows:
        by_bin.setdefault(r["bin"], {})[r["zone"]] = round(r["avg_n"], 2)
    bins = []
    for b, occ in sorted(by_bin.items()):
        total = sum(occ.values())
        bins.append({"minute_of_day": b, "avg_n": occ, "total": round(total, 1),
                     "share_pct": {z: (round(100 * n / total) if total else 0) for z, n in occ.items()}})
    peak = max(bins, key=lambda x: x["total"])
    return {"state": "ok", "basis": basis, "date": date, "weeks": None if date else weeks, "zones": zlist, "bins": bins,
            "peak": {"minute_of_day": peak["minute_of_day"], "total": peak["total"], "avg_n": peak["avg_n"]}}


# ---- 8. LLM 글 (reports.db, Phase 4b 가 채운다) ------------------------------------------------

@router.get("/text")
def text(date: str | None = Query(None, pattern=DATE)):
    date = date or _today()
    con = connect_reports_ro()
    if con is None:
        return _no("reports.db 가 아직 없다 — jobs/report.py 가 만든다", date=date, items=[])
    rows = con.execute("SELECT kind, headline, body, engine, model, ts created_at FROM reports "
                       "WHERE for_date = ? AND ok = 1 ORDER BY ts DESC", (date,)).fetchall()
    con.close()
    if not rows:
        return _no("그날의 글이 없다", date=date, items=[])
    return {"state": "ok", "basis": "reports", "date": date, "items": [dict(r) for r in rows]}
