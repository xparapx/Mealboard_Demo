"""인사이트 API 8종 — insights.db(집계) 와 reports.db(LLM 글) 를 읽기 전용으로 내준다.

공통 계약: `state: ok | no_data`, 무엇을 근거로 했는지 `basis` 동봉, insights.db 가 없으면 `no_data` + `reason` (파일을 만들지 않는다).
오늘은 창이 아직 열려 있으면 집계 행이 있어도 쓰지 않고 queue.db 로 즉석 계산한다 — `basis: live`
(14:10 타이머나 부팅 직후 타이머가 남긴 반쪽 행이 하루 종일 화면을 얼리지 않게). 즉석 창은 최근 LIVE_MIN 분이며 응답의 window 에 적는다.
집계 행은 .env FEED_SOURCE 와 같은 출처만 쓴다(insights.db 자체가 한 출처·한 창으로 묶인다 — rollup 의 meta 불변식).
이 엔드포인트들은 30초 폴링 대상이 아니다(화면 진입 시 1회, day·quality 만 5분).
"""
import datetime as dt
import json
from contextlib import closing

from fastapi import APIRouter, Query

from ..config import DB_PATH, FEED_SOURCE, ROLLUP_WINDOW, ZONES_JSON
from ..insight_calc import GOLDEN_WAIT, day_summary, golden_bins, median_or_none
from ..insights_db import connect_reports_ro, connect_ro, meta
from ..lunch import BUCKET_MIN, bounds, iso_at, minute_of_day, seconds_of_day, weekday_of
from ..mealjson import menu_on, nutrition_rows, read_meal
from .typical import MIN_BUCKETS
from vision.zones import load_zones, polygon_area_m2

router = APIRouter(prefix="/api/insight")
LIVE_MIN = 180                 # 오늘 즉석 계산에 쓰는 최근 분
MIN_DAYS = 2                   # 메뉴 통계가 뜻을 가지려면 이만큼은 나왔어야 한다 (menus 기본값·예보 보정 공통)
MENU_FACTOR = (0.7, 1.5)       # 예보 보정 클램프
NO_DB = "insights.db 가 아직 없다 — jobs/rollup.py 가 만든다"
WINDOW_LO, WINDOW_HI = bounds(ROLLUP_WINDOW)


def _no(reason, **extra):
    return {"state": "no_data", "reason": reason, **extra}


def _today():
    return dt.date.today().isoformat()


def _iso(date):
    return (date or dt.date.today()).isoformat()


def _since(weeks):
    return (dt.date.today() - dt.timedelta(weeks=weeks)).isoformat()


def _window():
    return {"lo": WINDOW_LO, "hi": WINDOW_HI, "name": ROLLUP_WINDOW}


def _rollup_meta():
    con = connect_ro()
    if con is None:
        return {"last_run": None, "schema_version": None}
    with closing(con):
        run = con.execute("SELECT finished_at FROM runs WHERE ok = 1 ORDER BY id DESC LIMIT 1").fetchone()
        return {"last_run": run["finished_at"] if run else None,
                "schema_version": con.execute("PRAGMA user_version").fetchone()[0]}


# ---- 하루치: 집계 행 또는 즉석 계산 -------------------------------------------------------------

def _stored_day(date):
    """insights.db 의 그날 행 + events + bins. 없으면 None"""
    con = connect_ro()
    if con is None:
        return None
    with closing(con):
        row = con.execute("SELECT * FROM lunch_days WHERE date = ? AND source = ?", (date, FEED_SOURCE)).fetchone()
        if row is None:
            return None
        summary = dict(row)
        summary["menu"] = json.loads(summary.pop("menu_json") or "[]")
        summary["events"] = [dict(r) for r in con.execute(
            "SELECT kind, start_ts, end_ts, minutes, value, detail FROM events WHERE date = ? ORDER BY start_ts", (date,))]
        summary["bins"] = [dict(r) for r in con.execute(
            "SELECT bin, n, ok_n, insufficient_n, avg_queue, max_queue, avg_rate, avg_wait, max_wait FROM lunch_bins WHERE date = ? ORDER BY bin", (date,))]
        return summary


def _live_day(date):
    """오늘 최근 LIVE_MIN 분(창 안)을 queue.db 에서 한 번 읽어 day_summary — 표본·커버리지가 같은 창을 본다"""
    now = dt.datetime.now()
    nmin = minute_of_day(now)
    lo, hi = max(WINDOW_LO, nmin - LIVE_MIN), min(WINDOW_HI, nmin + 1)
    samples = []
    con = connect_ro(DB_PATH, "samples")
    if con is not None and lo < hi:
        with closing(con):
            samples = [dict(r) for r in con.execute(
                "SELECT ts, queue_len, rate_per_min, wait_min, state FROM samples WHERE ts >= ? AND ts < ? ORDER BY ts",
                (iso_at(date, lo * 60), iso_at(date, hi * 60)))]
    s = day_summary(samples, date, lo, max(lo, hi), seconds_of_day(now))
    s["menu"] = menu_on(read_meal(), date)
    return s


def _day(date):
    """(basis, summary) — 오늘이고 창이 아직 열려 있으면 live, 아니면 집계 행, 오늘인데 행이 없으면 live, 그 밖엔 None"""
    today = date == _today()
    if today and minute_of_day(dt.datetime.now()) < WINDOW_HI:
        return "live", _live_day(date)
    stored = _stored_day(date)
    if stored is not None:
        return "rollup", stored
    if today:
        return "live", _live_day(date)
    return None, None


# ---- 1. 요일×시각 히트맵 -----------------------------------------------------------------

@router.get("/heatmap")
def heatmap(weeks: int = Query(4, ge=1, le=12)):
    con = connect_ro()
    if con is None:
        return _no(NO_DB, cells=[], window=_window())
    with closing(con):
        rows = con.execute(
            "SELECT b.weekday, b.bin, AVG(b.avg_wait) w, AVG(b.avg_queue) q, COUNT(DISTINCT b.date) d "
            "FROM lunch_bins b JOIN lunch_days l ON l.date = b.date "
            "WHERE l.source = ? AND b.date >= ? GROUP BY b.weekday, b.bin ORDER BY b.weekday, b.bin", (FEED_SOURCE, _since(weeks))).fetchall()
        days = con.execute("SELECT COUNT(*) FROM lunch_days WHERE source = ? AND date >= ?", (FEED_SOURCE, _since(weeks))).fetchone()[0]
    if not rows:
        return _no("집계된 날이 없다", cells=[], window=_window(), days=0)
    return {"state": "ok", "basis": "weekday" if days >= 5 else "recent", "weeks": weeks, "days": days,
            "bucket_min": BUCKET_MIN, "window": _window(), "source": FEED_SOURCE,
            "cells": [{"weekday": r["weekday"], "minute_of_day": r["bin"],
                       "wait_min": round(r["w"], 1) if r["w"] is not None else None,
                       "queue": round(r["q"], 1) if r["q"] is not None else None, "n_days": r["d"]} for r in rows]}


# ---- 2. 하루 -----------------------------------------------------------------------------

@router.get("/day")
def day(date: dt.date | None = Query(None)):
    date = _iso(date)
    basis, s = _day(date)
    if s is None:
        return _no(NO_DB if connect_ro() is None else "그날의 집계가 없다", date=date)
    events, bins = s.pop("events"), s.pop("bins")
    menu = s.pop("menu")
    if basis == "live" and not s["n_samples"]:
        return _no("최근 표본이 없다", basis="live", date=date, summary=s, menu=menu, events=events, bins=bins)
    return {"state": "ok", "basis": basis, "date": date, "summary": s, "menu": menu,
            "golden": [e for e in events if e["kind"] == "golden"],
            "bottlenecks": [e for e in events if e["kind"] == "bottleneck"], "events": events, "bins": bins}


# ---- 3. 메뉴 인기 ---------------------------------------------------------------------------

@router.get("/menus")
def menus(n: int = Query(5, ge=1, le=20), min_days: int = Query(MIN_DAYS, ge=1, le=30)):
    con = connect_ro()
    if con is None:
        return _no(NO_DB, items=[])
    with closing(con):
        rows = con.execute(
            "SELECT menu, n_days, popularity, avg_rise_rate, avg_peak_wait, last_date FROM menu_stats "
            "WHERE n_days >= ? AND popularity IS NOT NULL ORDER BY popularity DESC, n_days DESC LIMIT ?", (min_days, n)).fetchall()
        m = meta(con)
    base = {k: (float(m[k]) if m.get(k) not in (None, "") else None) for k in ("menu_base_rise", "menu_base_wait")}
    if not rows:
        return _no(f"{min_days}일 이상 나온 메뉴가 아직 없다", items=[], baseline=base)
    return {"state": "ok", "basis": "menu_stats", "min_days": min_days, "baseline": base, "items": [dict(r) for r in rows]}


# ---- 4. 예보 ----------------------------------------------------------------------------

def _typical_curve(con, date, weeks):
    """같은 요일 최근 N주 → 모자라면 최근 7일(요일 무관). 예보 대상 날 자신은 뺀다(비교 대상이 자기 자신이 되면 안 된다).
    (basis, [{minute_of_day, wait}])"""
    plans = [("weekday", "AND b.weekday = ? AND b.date >= ?", (weekday_of(date), _since(weeks))),
             ("recent", "AND b.date >= ?", ((dt.date.today() - dt.timedelta(days=7)).isoformat(),))]
    for basis, cond, args in plans:
        rows = con.execute(
            "SELECT b.bin, AVG(b.avg_wait) w FROM lunch_bins b JOIN lunch_days l ON l.date = b.date "
            f"WHERE l.source = ? AND b.date != ? AND b.avg_wait IS NOT NULL {cond} GROUP BY b.bin ORDER BY b.bin",
            (FEED_SOURCE, date, *args)).fetchall()
        if len(rows) >= MIN_BUCKETS:
            return basis, [{"minute_of_day": r["bin"], "wait": round(r["w"], 1)} for r in rows]
    return None, []


def _menu_factor(con, dishes):
    """그날 메뉴의 인기 지수 평균/100 을 0.7~1.5 로 눌러서. MIN_DAYS 미만인 메뉴는 menus 와 같이 무시"""
    if not dishes:
        return 1.0, []
    marks = ",".join("?" * len(dishes))
    rows = con.execute(f"SELECT menu, popularity, n_days FROM menu_stats WHERE popularity IS NOT NULL AND n_days >= ? AND menu IN ({marks})",
                       (MIN_DAYS, *dishes)).fetchall()
    if not rows:
        return 1.0, []
    f = sum(r["popularity"] for r in rows) / len(rows) / 100
    return round(min(max(f, MENU_FACTOR[0]), MENU_FACTOR[1]), 2), [dict(r) for r in rows]


@router.get("/forecast")
def forecast(date: dt.date | None = Query(None), weeks: int = Query(4, ge=1, le=12)):
    if date is None:                                          # 급식이 끝난 뒤면 내일, 아니면 오늘
        now = dt.datetime.now()
        date = now.date() if minute_of_day(now) < WINDOW_HI else now.date() + dt.timedelta(days=1)
    if date.weekday() >= 5:
        return {"state": "no_meal", "date": date.isoformat(), "reason": "주말에는 급식이 없다", "curve": [], "golden": []}
    date = date.isoformat()
    con = connect_ro()
    if con is None:
        return _no(NO_DB, date=date, curve=[], golden=[])
    dishes = menu_on(read_meal(), date)
    with closing(con):
        basis, typical = _typical_curve(con, date, weeks)
        factor, matched = _menu_factor(con, dishes)
    if not typical:
        return _no("평소 곡선을 만들 집계가 아직 모자란다", date=date, curve=[], golden=[], menu=dishes)
    curve = [{"minute_of_day": p["minute_of_day"], "typical_wait": p["wait"], "forecast_wait": round(p["wait"] * factor, 1)} for p in typical]
    peak = max(curve, key=lambda p: p["forecast_wait"])
    return {"state": "ok", "basis": basis, "date": date, "weeks": weeks, "menu": dishes, "menu_factor": factor, "menu_matched": matched,
            "formula": f"forecast = typical({basis}) × menu_factor(인기 지수 평균/100, {MENU_FACTOR[0]}~{MENU_FACTOR[1]} 클램프); "
                       f"golden = forecast ≤ {GOLDEN_WAIT}분",
            "peak": {"minute_of_day": peak["minute_of_day"], "wait_min": peak["forecast_wait"]},
            "golden": golden_bins(curve), "curve": curve}


# ---- 5. 측정 품질 --------------------------------------------------------------------------

@router.get("/quality")
def quality(date: dt.date | None = Query(None)):
    date = _iso(date)
    basis, s = _day(date)
    rollup = _rollup_meta()
    if s is None:
        return _no(NO_DB if rollup["schema_version"] is None else "그날의 집계가 없다", date=date, rollup=rollup)
    out = {"state": "ok" if s["n_samples"] else "no_data", "basis": basis, "date": date,
           "window": {"lo": s["window_lo"], "hi": s["window_hi"]},
           "coverage_pct": s["coverage_pct"], "stale_min": s["stale_min"], "insufficient_min": s["insufficient_min"],
           "n_samples": s["n_samples"],
           "gaps": [{"start_ts": e["start_ts"], "end_ts": e["end_ts"], "minutes": e["minutes"]} for e in s["events"] if e["kind"] == "stale"],
           "rollup": rollup}
    if not s["n_samples"]:
        out["reason"] = "최근 표본이 없다"
    return out


# ---- 6. 주간 영양 --------------------------------------------------------------------------

def _week_key(date):
    d = dt.date.fromisoformat(date)
    return (d - dt.timedelta(days=d.weekday())).isoformat()       # 그 주 월요일


def _weeks_from(days):
    """nutrition_days 모양의 행들 → 주별 평균"""
    weeks = {}
    for d in days:
        weeks.setdefault(_week_key(d["date"]), []).append(d)

    def avg(rows, k):
        v = [r[k] for r in rows if r.get(k) is not None]
        return round(sum(v) / len(v), 1) if v else None
    return [{"week": w, "days": len(rows), "kcal": avg(rows, "kcal"), "energy_pct": avg(rows, "energy_pct"), "mar": avg(rows, "mar"),
             "macro_ok_days": sum(1 for r in rows if r.get("macro_ok")),
             "carb_pct": avg(rows, "carb_ratio"), "protein_pct": avg(rows, "protein_ratio"), "fat_pct": avg(rows, "fat_ratio")}
            for w, rows in sorted(weeks.items())]


@router.get("/nutrition")
def nutrition(weeks: int = Query(8, ge=1, le=26)):
    con = connect_ro()
    if con is not None:
        with closing(con):
            rows = con.execute("SELECT * FROM nutrition_days WHERE date >= ? ORDER BY date", (_since(weeks),)).fetchall()
        if rows:
            return {"state": "ok", "basis": "nutrition_days", "weeks": _weeks_from([dict(r) for r in rows])}
    week = nutrition_rows(read_meal())                        # 집계가 없으면 meal.json 의 이번 주만
    if not week:
        return _no("영양 이력도 이번 주 식단도 없다", weeks=[])
    return {"state": "ok", "basis": "meal_json", "weeks": _weeks_from(week)}


# ---- 7. 구역 점유율 --------------------------------------------------------------------------

@router.get("/zones")
def zones(weeks: int = Query(4, ge=1, le=12), date: dt.date | None = Query(None)):
    date = date.isoformat() if date else None
    try:
        doc = load_zones(ZONES_JSON)
    except (OSError, ValueError) as e:
        return _no(f"zones.json 문제: {e}", zones=[], bins=[])
    zlist = [{"id": z["id"], "label": z["name"], "area_m2": round(polygon_area_m2(z["polygon"], doc["floor"]), 1),
              "polygon": z["polygon"]} for z in doc["zones"]]      # 구역 정의(정규화 다각형)는 설정이지 개인정보가 아니다 — 화면이 평면도 위에 틴트를 그린다
    con = connect_ro()
    if con is None:
        return _no(NO_DB, zones=zlist, bins=[])
    with closing(con):
        if date:
            rows = con.execute("SELECT z.bin, z.zone, z.avg_n FROM zone_bins z JOIN lunch_days l ON l.date = z.date "
                               "WHERE z.date = ? AND l.source = ? ORDER BY z.bin", (date, FEED_SOURCE)).fetchall()
            basis = "day"
        else:
            rows = con.execute("SELECT z.bin, z.zone, AVG(z.avg_n) avg_n FROM zone_bins z JOIN lunch_days l ON l.date = z.date "
                               "WHERE z.date >= ? AND l.source = ? GROUP BY z.bin, z.zone ORDER BY z.bin", (_since(weeks), FEED_SOURCE)).fetchall()
            basis = "recent"
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
    return {"state": "ok", "basis": basis, "date": date, "weeks": None if date else weeks, "window": _window(), "zones": zlist, "bins": bins,
            "peak": {"minute_of_day": peak["minute_of_day"], "total": peak["total"], "avg_n": peak["avg_n"]}}


# ---- 8. LLM 글 (reports.db, Phase 4b 가 채운다) ------------------------------------------------

@router.get("/text")
def text(date: dt.date | None = Query(None)):
    date = _iso(date)
    con = connect_reports_ro()
    if con is None:
        return _no("reports.db 가 아직 없다 — jobs/report.py 가 만든다", date=date, items=[])
    with closing(con):
        rows = con.execute("SELECT kind, headline, body, engine, model, ts created_at FROM reports "
                           "WHERE for_date = ? AND ok = 1 ORDER BY ts DESC", (date,)).fetchall()
    if not rows:
        return _no("그날의 글이 없다", date=date, items=[])
    return {"state": "ok", "basis": "reports", "date": date, "items": [dict(r) for r in rows]}
