"""하루 단위 집계 → data/insights.db. 이 파일이 insights.db 의 유일한 writer 다 (공개 app 은 SELECT 만).

읽기: queue.db 의 samples·zone_samples(읽기 전용 연결) + data/meal.json(이번 주 식단·영양 → nutrition_days 에 이력으로 쌓는다)
쓰기: lunch_days · lunch_bins · zone_bins · events · menu_days 는 날짜 단위 DELETE→INSERT 를 한 트랜잭션으로,
      menu_stats 는 매 실행 전체 재생성, runs 에 실행 기록. 개별 좌표·궤적은 어디에도 없다 — 구역별 인원수만 (CLAUDE.md §2).

실행:  uv run python -m jobs.rollup                  # 오늘·어제 (--days 2)
       uv run python -m jobs.rollup --date 2026-09-03
       uv run python -m jobs.rollup --all            # queue.db 의 모든 날짜. 실행 전 insights.db 를 .bak-<시각> 으로 복사하고 되돌리는 명령을 찍는다
       --window lunch|all (.env ROLLUP_WINDOW) · --source mock|vision (.env FEED_SOURCE) · --dry-run (아무 파일도 만들거나 바꾸지 않는다)
systemd: mealboard-rollup.timer 가 14:10 에 --days 2 로 부른다.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sqlite3
import statistics
import sys
import time

from app.config import DATA, DB_PATH, FEED_SOURCE, INSIGHTS_DB_PATH, MEAL_JSON, ROLLUP_WINDOW
from app.insight_calc import CALC_VERSION, bin_zones, day_summary, normalize_menu, popularity
from app.lunch import WINDOWS, bounds, seconds_of_day

SCHEMA_VERSION = 1
LOCK = DATA / "rollup.lock"
LOCK_STALE_SEC = 3600           # 이보다 오래된 잠금은 죽은 프로세스가 남긴 것으로 본다

SCHEMA = """
CREATE TABLE IF NOT EXISTS lunch_days (
  date TEXT PRIMARY KEY, weekday INTEGER NOT NULL,          -- weekday: SQLite strftime('%w') 규칙, 0=일요일
  window_lo INTEGER, window_hi INTEGER, source TEXT,        -- 창(자정부터 분), source: mock | vision
  n_samples INTEGER, coverage_pct REAL, stale_min REAL, insufficient_min REAL, first_ts TEXT, last_ts TEXT,
  peak_wait REAL, peak_wait_ts TEXT, peak_queue INTEGER, peak_queue_ts TEXT, avg_wait REAL,
  served_est INTEGER, typical_rate REAL, rise_rate REAL, golden_min REAL, bottleneck_min REAL,
  menu_json TEXT, main_dish TEXT, calc_version INTEGER, computed_at TEXT
);
CREATE TABLE IF NOT EXISTS lunch_bins (
  date TEXT, weekday INTEGER, bin INTEGER, n INTEGER, ok_n INTEGER, insufficient_n INTEGER,
  avg_queue REAL, max_queue INTEGER, avg_rate REAL, avg_wait REAL, max_wait REAL, PRIMARY KEY (date, bin)
);
CREATE INDEX IF NOT EXISTS idx_lunch_bins_weekday ON lunch_bins (weekday, bin);
CREATE TABLE IF NOT EXISTS zone_bins (
  date TEXT, bin INTEGER, zone TEXT, n INTEGER, avg_n REAL, max_n INTEGER, PRIMARY KEY (date, bin, zone)
);
CREATE TABLE IF NOT EXISTS events (
  date TEXT, kind TEXT, start_ts TEXT, end_ts TEXT, minutes REAL, value REAL, detail TEXT,   -- kind: golden|bottleneck|stale|insufficient
  PRIMARY KEY (date, kind, start_ts)
);
CREATE TABLE IF NOT EXISTS menu_days (
  date TEXT, menu TEXT, position INTEGER, peak_wait REAL, rise_rate REAL, peak_queue INTEGER, served_est INTEGER,
  PRIMARY KEY (date, menu)
);
CREATE TABLE IF NOT EXISTS menu_stats (
  menu TEXT PRIMARY KEY, n_days INTEGER, avg_peak_wait REAL, avg_rise_rate REAL, avg_peak_queue REAL,
  popularity INTEGER, first_date TEXT, last_date TEXT
);
CREATE TABLE IF NOT EXISTS nutrition_days (
  date TEXT PRIMARY KEY, kcal REAL, energy_pct INTEGER, protein_pct INTEGER,
  carb_ratio INTEGER, protein_ratio INTEGER, fat_ratio INTEGER, macro_ok INTEGER, mar INTEGER, kgco2e REAL,
  menu_json TEXT, fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, finished_at TEXT, args TEXT, dates TEXT,
  n_days INTEGER, ok INTEGER, error TEXT
);
"""


# ---- 읽기 (queue.db, meal.json) ----------------------------------------------------

def open_queue():
    """queue.db 읽기 전용 연결. 파일이 없으면 None — 만들지 않는다(쓰기 주체는 vision/mock 뿐)"""
    if not DB_PATH.exists():
        return None
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def list_dates(qcon):
    return [r[0] for r in qcon.execute("SELECT DISTINCT substr(ts, 1, 10) FROM samples ORDER BY 1")]


def read_day(qcon, date):
    """그날의 samples 와 zone_samples 를 dict 리스트로. ts 는 로컬 ISO 라 문자열 비교로 하루가 잘린다"""
    nxt = (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()
    samples = [dict(r) for r in qcon.execute(
        "SELECT ts, queue_len, rate_per_min, wait_min, state FROM samples WHERE ts >= ? AND ts < ? ORDER BY ts", (date, nxt))]
    zones = [dict(r) for r in qcon.execute(
        "SELECT ts, zone, n FROM zone_samples WHERE ts >= ? AND ts < ? ORDER BY ts", (date, nxt))]
    return samples, zones


def read_meal():
    if not MEAL_JSON.exists():
        return None
    try:
        return json.loads(MEAL_JSON.read_text(encoding="utf-8"))
    except ValueError:
        return None


# ---- 쓰기 (insights.db) ---------------------------------------------------------------

def migrate(con):
    """PRAGMA user_version 으로 스키마 판. 0 = 새 파일"""
    v = con.execute("PRAGMA user_version").fetchone()[0]
    if v == 0:
        con.executescript(SCHEMA)
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        con.commit()
    elif v != SCHEMA_VERSION:
        raise SystemExit(f"insights.db 스키마 판 {v} 는 이 코드({SCHEMA_VERSION})와 맞지 않는다")


def upsert_nutrition(con, meal):
    """meal.json 의 week[] 를 nutrition_days 에 쌓는다 — 캐시는 이번 주뿐이지만 여기엔 이력이 남는다"""
    n = 0
    for d in (meal or {}).get("week") or []:
        a = d.get("assess") or {}
        ratio = a.get("macro_ratio") or {}
        date = f"{d['date'][:4]}-{d['date'][4:6]}-{d['date'][6:8]}"
        con.execute("INSERT OR REPLACE INTO nutrition_days VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (date, d.get("kcal"), a.get("energy_pct"), a.get("protein_pct"),
                     ratio.get("carb"), ratio.get("protein"), ratio.get("fat"),
                     None if a.get("macro_ratio_ok") is None else int(a["macro_ratio_ok"]), a.get("mar"),
                     (d.get("carbon") or {}).get("kgco2e"),
                     json.dumps(d.get("menu") or [], ensure_ascii=False), meal.get("fetched_at")))
        n += 1
    return n


def menu_for(con, date):
    row = con.execute("SELECT menu_json FROM nutrition_days WHERE date = ?", (date,)).fetchone()
    return json.loads(row[0]) if row else []


def write_day(con, s, zone_rows, menu, source, weekday):
    """하루치 행을 지우고 다시 쓴다 — 한 트랜잭션. 같은 날을 두 번 돌려도 행 수가 변하지 않는다"""
    date = s["date"]
    dishes = [m for m in (normalize_menu(x) for x in menu) if m]
    for t in ("lunch_days", "lunch_bins", "zone_bins", "events", "menu_days"):
        con.execute(f"DELETE FROM {t} WHERE date = ?", (date,))
    con.execute("INSERT INTO lunch_days VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (date, weekday, s["window_lo"], s["window_hi"], source, s["n_samples"], s["coverage_pct"], s["stale_min"],
                 s["insufficient_min"], s["first_ts"], s["last_ts"], s["peak_wait"], s["peak_wait_ts"], s["peak_queue"],
                 s["peak_queue_ts"], s["avg_wait"], s["served_est"], s["typical_rate"], s["rise_rate"], s["golden_min"],
                 s["bottleneck_min"], json.dumps(dishes, ensure_ascii=False), dishes[0] if dishes else None,
                 CALC_VERSION, dt.datetime.now().isoformat(timespec="seconds")))
    con.executemany("INSERT INTO lunch_bins VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [(date, weekday, b["bin"], b["n"], b["ok_n"], b["insufficient_n"], b["avg_queue"], b["max_queue"],
                      b["avg_rate"], b["avg_wait"], b["max_wait"]) for b in s["bins"]])
    con.executemany("INSERT INTO zone_bins VALUES (?,?,?,?,?,?)",
                    [(date, z["bin"], z["zone"], z["n"], z["avg_n"], z["max_n"]) for z in bin_zones(zone_rows)])
    con.executemany("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?)",
                    [(date, e["kind"], e["start_ts"], e["end_ts"], e["minutes"], e["value"], e["detail"]) for e in s["events"]])
    con.executemany("INSERT OR REPLACE INTO menu_days VALUES (?,?,?,?,?,?,?)",
                    [(date, m, i, s["peak_wait"], s["rise_rate"], s["peak_queue"], s["served_est"]) for i, m in enumerate(dishes)])
    con.commit()


def rebuild_menu_stats(con):
    """menu_days 전체에서 메뉴별 평균과 인기 지수를 다시 만든다. 기준(base)은 메뉴별 평균의 중앙값"""
    rows = con.execute(
        "SELECT menu, COUNT(*) n, AVG(peak_wait) w, AVG(rise_rate) r, AVG(peak_queue) q, MIN(date) f, MAX(date) l "
        "FROM menu_days WHERE peak_wait IS NOT NULL GROUP BY menu").fetchall()
    base_w = statistics.median([r[2] for r in rows if r[2] is not None]) if any(r[2] is not None for r in rows) else None
    base_r = statistics.median([r[3] for r in rows if r[3] is not None]) if any(r[3] is not None for r in rows) else None
    con.execute("DELETE FROM menu_stats")
    con.executemany("INSERT INTO menu_stats VALUES (?,?,?,?,?,?,?,?)",
                    [(m, n, round(w, 1) if w is not None else None, round(r, 2) if r is not None else None,
                      round(q, 1) if q is not None else None, popularity(r, w, base_r, base_w), f, l)
                     for m, n, w, r, q, f, l in rows])
    con.commit()
    return len(rows)


# ---- 실행 --------------------------------------------------------------------------

def acquire_lock():
    """data/rollup.lock — 타이머와 손 실행이 겹치지 않게. 죽은 잠금(1시간 초과)은 치우고 잡는다"""
    for _ in range(2):
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return
        except FileExistsError:
            if time.time() - LOCK.stat().st_mtime < LOCK_STALE_SEC:
                raise SystemExit(f"다른 rollup 이 실행 중이다 ({LOCK}). 1시간이 지나면 죽은 잠금으로 보고 치운다")
            LOCK.unlink()


def pick_dates(a, qcon):
    if a.date:
        return [a.date]
    if a.all:
        return list_dates(qcon)
    today = dt.date.today()
    return [(today - dt.timedelta(days=i)).isoformat() for i in range(a.days)][::-1]


def weekday_of(date):
    return (dt.date.fromisoformat(date).weekday() + 1) % 7      # SQLite strftime('%w') 와 같은 규칙


def main():
    ap = argparse.ArgumentParser(description="queue.db → insights.db 하루 단위 집계")
    ap.add_argument("--date", help="YYYY-MM-DD 하루만")
    ap.add_argument("--days", type=int, default=2, help="오늘부터 거슬러 N일 (기본 2)")
    ap.add_argument("--all", action="store_true", help="queue.db 의 모든 날짜 (백업 후)")
    ap.add_argument("--window", choices=WINDOWS, default=ROLLUP_WINDOW)
    ap.add_argument("--source", choices=["mock", "vision"], default=FEED_SOURCE)
    ap.add_argument("--dry-run", action="store_true", help="계산만 하고 아무것도 쓰지 않는다")
    a = ap.parse_args()

    qcon = open_queue()
    if qcon is None:
        print(f"{DB_PATH} 가 없다 - 집계할 표본이 없다")
        return 0
    dates = pick_dates(a, qcon)
    if not dates:
        print("집계할 날짜가 없다 (--all 인데 samples 가 비어 있다). 아무것도 하지 않는다")
        return 0
    lo, hi = bounds(a.window)
    today = dt.date.today().isoformat()
    now_sec = seconds_of_day(dt.datetime.now())
    meal = read_meal()

    if a.dry_run:
        print(f"[dry-run] window={a.window} {lo}~{hi}분 source={a.source} 날짜 {len(dates)}개 - 파일을 만들거나 바꾸지 않는다")
        for date in dates:
            samples, zones = read_day(qcon, date)
            s = day_summary(samples, date, lo, hi, now_sec if date == today else None)
            report(s, zones)
        return 0

    if a.all and INSIGHTS_DB_PATH.exists():
        bak = INSIGHTS_DB_PATH.with_name(f"{INSIGHTS_DB_PATH.name}.bak-{dt.datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(INSIGHTS_DB_PATH, bak)
        print(f"백업 {bak.name}  되돌리기: cp {bak} {INSIGHTS_DB_PATH}")

    acquire_lock()
    started = dt.datetime.now().isoformat(timespec="seconds")
    con = sqlite3.connect(INSIGHTS_DB_PATH, timeout=5)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        migrate(con)
        con.execute("INSERT INTO runs (started_at, args, dates) VALUES (?,?,?)",
                    (started, " ".join(sys.argv[1:]), ",".join(dates)))
        run_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.commit()
        n_days, err = 0, None
        try:
            upsert_nutrition(con, meal)
            con.commit()
            for date in dates:
                samples, zones = read_day(qcon, date)
                if not samples:
                    print(f"{date}  표본 없음 - 건너뜀")
                    continue
                s = day_summary(samples, date, lo, hi, now_sec if date == today else None)
                write_day(con, s, zones, menu_for(con, date), a.source, weekday_of(date))
                report(s, zones)
                n_days += 1
            print(f"menu_stats {rebuild_menu_stats(con)}개 메뉴")
        except Exception as e:                       # 실패도 runs 에 남긴다
            con.rollback()
            err = f"{type(e).__name__}: {e}"
            raise
        finally:
            con.execute("UPDATE runs SET finished_at=?, n_days=?, ok=?, error=? WHERE id=?",
                        (dt.datetime.now().isoformat(timespec="seconds"), n_days, int(err is None), err, run_id))
            con.commit()
    finally:
        con.close()
        LOCK.unlink(missing_ok=True)
    return 0


def report(s, zones):
    ev = {}
    for e in s["events"]:
        ev[e["kind"]] = ev.get(e["kind"], 0) + 1
    print(f"{s['date']}  표본 {s['n_samples']}  커버리지 {s['coverage_pct']}%  최대 대기 {s['peak_wait']}분@{(s['peak_wait_ts'] or '')[11:16]}  "
          f"처리 {s['served_est']}명  황금 {s['golden_min']}분  병목 {s['bottleneck_min']}분  구역행 {len(zones)}  이벤트 {ev}")


if __name__ == "__main__":
    sys.exit(main())
