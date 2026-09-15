"""하루 단위 집계 → data/insights.db. 이 파일이 insights.db 의 유일한 writer 다 (공개 app 은 SELECT 만).

읽기: queue.db 의 samples·zone_samples(읽기 전용 연결) + data/meal.json(이번 주 식단·영양 → nutrition_days 에 이력으로 쌓는다)
쓰기: lunch_days · lunch_bins · zone_bins · events · menu_days 는 날짜 단위 DELETE→INSERT 를 한 트랜잭션으로,
      menu_stats 는 매 실행 전체 재생성, meta 에 창·출처·인기 기준값, runs 에 실행 기록.
      개별 좌표·궤적은 어디에도 없다 — 구역별 인원수만 (CLAUDE.md §2).
불변식: insights.db 하나는 한 창 모드(window)·한 출처(source)로만 채운다. 처음 쓸 때 meta 에 적고, 다른 설정으로 부르면 거부한다 —
      mock 표본이 실측 히트맵에 섞이거나 새벽 구간이 평소 곡선에 들어가지 않게. 설정을 바꾸려면 파일을 .bak-<시각> 으로 이름 바꾸고 새로 시작(PLAN §2.5).
끼니(09-16 중식/석식 분리): window=lunch 면 하루를 중식(LUNCH_*)·석식(DINNER_*) 두 창으로 각각 집계해 meal 열(lunch|dinner)로 나눠 담는다.
      window=all(스테이징 mock)은 하루 전체 한 행(meal='all'). 표 이름 lunch_* 는 역사적 이름 — 지금은 끼니 공용이다.
동시 실행: 잠금 파일을 두지 않는다. 날짜 단위 트랜잭션은 SQLite 가 직렬화하고 결과가 같으므로 타이머와 손 실행이 겹쳐도 해가 없다.

실행:  uv run python -m jobs.rollup                  # 오늘·어제 (--days 2)
       uv run python -m jobs.rollup --date 2026-09-03
       uv run python -m jobs.rollup --all            # queue.db 의 모든 날짜. 실행 전 insights.db 를 .bak-<시각> 으로 복사하고 되돌리는 명령을 찍는다
       --window lunch|all (.env ROLLUP_WINDOW) · --source mock|vision (.env FEED_SOURCE) · --dry-run (아무 파일도 만들거나 바꾸지 않는다)
systemd: mealboard-rollup.timer 가 14:10 에 --days 2 로 부른다.
"""
import argparse
import datetime as dt
import json
import sqlite3
import sys

from app.config import DB_PATH, FEED_SOURCE, INSIGHTS_DB_PATH, ROLLUP_WINDOW
from app.insight_calc import CALC_VERSION, bin_zones, day_summary, median_or_none, normalize_menu, popularity
from app.insights_db import connect_ro, meta
from app.lunch import WINDOWS, agg_meals, seconds_of_day, weekday_of
from app.mealjson import nutrition_rows, read_meal

SCHEMA_VERSION = 2                 # v2(09-16): 끼니(meal) 열 — lunch|dinner|all. v1 파일은 백업 후 --all 재집계
SOURCES = ("mock", "vision")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);            -- window·source·menu_base_*_<meal>
CREATE TABLE IF NOT EXISTS lunch_days (
  date TEXT, meal TEXT, weekday INTEGER NOT NULL,           -- weekday: SQLite strftime('%w') 규칙, 0=일요일. meal: lunch|dinner|all
  window_lo INTEGER, window_hi INTEGER, source TEXT,        -- 창(자정부터 분), source: mock | vision
  n_samples INTEGER, coverage_pct REAL, stale_min REAL, insufficient_min REAL, first_ts TEXT, last_ts TEXT,
  peak_wait REAL, peak_wait_ts TEXT, peak_queue INTEGER, peak_queue_ts TEXT, avg_wait REAL,
  served_est INTEGER, typical_rate REAL, rise_rate REAL, golden_min REAL, bottleneck_min REAL,
  menu_json TEXT, main_dish TEXT, calc_version INTEGER, computed_at TEXT,
  PRIMARY KEY (date, meal)
);
CREATE TABLE IF NOT EXISTS lunch_bins (
  date TEXT, meal TEXT, weekday INTEGER, bin INTEGER, n INTEGER, ok_n INTEGER, insufficient_n INTEGER,
  avg_queue REAL, max_queue INTEGER, avg_rate REAL, avg_wait REAL, max_wait REAL, PRIMARY KEY (date, meal, bin)
);
CREATE INDEX IF NOT EXISTS idx_lunch_bins_weekday ON lunch_bins (meal, weekday, bin);
CREATE TABLE IF NOT EXISTS zone_bins (
  date TEXT, meal TEXT, bin INTEGER, zone TEXT, n INTEGER, avg_n REAL, max_n INTEGER, PRIMARY KEY (date, meal, bin, zone)
);
CREATE TABLE IF NOT EXISTS events (
  date TEXT, meal TEXT, kind TEXT, start_ts TEXT, end_ts TEXT, minutes REAL, value REAL, detail TEXT,   -- kind: golden|bottleneck|stale|insufficient
  PRIMARY KEY (date, meal, kind, start_ts)
);
CREATE TABLE IF NOT EXISTS menu_days (
  date TEXT, meal TEXT, menu TEXT, position INTEGER, peak_wait REAL, rise_rate REAL, peak_queue INTEGER, served_est INTEGER,
  PRIMARY KEY (date, meal, menu)
);
CREATE TABLE IF NOT EXISTS menu_stats (
  meal TEXT, menu TEXT, n_days INTEGER, avg_peak_wait REAL, avg_rise_rate REAL, avg_peak_queue REAL,
  popularity INTEGER, first_date TEXT, last_date TEXT, PRIMARY KEY (meal, menu)
);
CREATE TABLE IF NOT EXISTS nutrition_days (
  date TEXT, meal TEXT, kcal REAL, energy_pct INTEGER, protein_pct INTEGER,
  carb_ratio INTEGER, protein_ratio INTEGER, fat_ratio INTEGER, macro_ok INTEGER, mar INTEGER, kgco2e REAL,
  menu_json TEXT, fetched_at TEXT, PRIMARY KEY (date, meal)
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, finished_at TEXT, args TEXT, dates TEXT,
  n_days INTEGER, ok INTEGER, error TEXT
);
"""


# ---- 읽기 (queue.db) ----------------------------------------------------------------

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


# ---- 쓰기 (insights.db) ---------------------------------------------------------------

def migrate(con):
    """PRAGMA user_version 으로 스키마 판. 0 = 새 파일"""
    v = con.execute("PRAGMA user_version").fetchone()[0]
    if v == 0:
        con.executescript(SCHEMA)
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        con.commit()
    elif v != SCHEMA_VERSION:
        raise SystemExit(f"insights.db 스키마 판 {v} 는 이 코드({SCHEMA_VERSION})와 맞지 않는다 — "
                         f"파일을 .bak-<시각> 으로 이름 바꾸고 --all 로 재집계한다(v2: meal 열, 09-16)")


def set_meta(con, **kv):
    con.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)", [(k, None if v is None else str(v)) for k, v in kv.items()])


def check_meta(con, window, source):
    """한 파일 = 한 창 모드·한 출처. 처음이면 적고, 다르면 거부한다 (끼니별 lo/hi 는 각 행의 window_lo/hi 에)"""
    want = {"window": window, "source": source}
    have = {k: v for k, v in meta(con).items() if k in want}
    if have and have != want:
        raise SystemExit(f"insights.db 는 {have} 로 만들어졌다 — 지금 설정 {want} 과 다르다. "
                         f"바꾸려면 파일을 .bak-<시각> 으로 이름 바꾸고 새로 시작한다(PLAN §2.5)")
    set_meta(con, **want)
    con.commit()


def upsert_nutrition(con, meal):
    """meal.json 의 week[] 를 nutrition_days 에 쌓는다 — 캐시는 이번 주뿐이지만 여기엔 이력이 남는다"""
    rows = nutrition_rows(meal)
    con.executemany("INSERT OR REPLACE INTO nutrition_days VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(r["date"], r["meal"], r["kcal"], r["energy_pct"], r["protein_pct"], r["carb_ratio"], r["protein_ratio"], r["fat_ratio"],
                      r["macro_ok"], r["mar"], r["kgco2e"], json.dumps(r["menu"], ensure_ascii=False), r["fetched_at"]) for r in rows])
    return len(rows)


def menu_for(con, date, meal_name):
    """그날·그 끼니의 메뉴. meal='all'(스테이징) 은 중식 메뉴를 쓴다"""
    row = con.execute("SELECT menu_json FROM nutrition_days WHERE date = ? AND meal = ?",
                      (date, "lunch" if meal_name == "all" else meal_name)).fetchone()
    return json.loads(row[0]) if row else []


def write_day(con, s, zone_rows, menu, source, meal_name):
    """그날·그 끼니의 행을 지우고 다시 쓴다 — 한 트랜잭션. 같은 날을 두 번 돌려도 행 수가 변하지 않는다"""
    date, weekday = s["date"], weekday_of(s["date"])
    dishes = [m for m in (normalize_menu(x) for x in menu) if m]
    for t in ("lunch_days", "lunch_bins", "zone_bins", "events", "menu_days"):
        con.execute(f"DELETE FROM {t} WHERE date = ? AND meal = ?", (date, meal_name))
    con.execute("INSERT INTO lunch_days VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (date, meal_name, weekday, s["window_lo"], s["window_hi"], source, s["n_samples"], s["coverage_pct"], s["stale_min"],
                 s["insufficient_min"], s["first_ts"], s["last_ts"], s["peak_wait"], s["peak_wait_ts"], s["peak_queue"],
                 s["peak_queue_ts"], s["avg_wait"], s["served_est"], s["typical_rate"], s["rise_rate"], s["golden_min"],
                 s["bottleneck_min"], json.dumps(dishes, ensure_ascii=False), dishes[0] if dishes else None,
                 CALC_VERSION, dt.datetime.now().isoformat(timespec="seconds")))
    con.executemany("INSERT INTO lunch_bins VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(date, meal_name, weekday, b["bin"], b["n"], b["ok_n"], b["insufficient_n"], b["avg_queue"], b["max_queue"],
                      b["avg_rate"], b["avg_wait"], b["max_wait"]) for b in s["bins"]])
    con.executemany("INSERT INTO zone_bins VALUES (?,?,?,?,?,?,?)",
                    [(date, meal_name, z["bin"], z["zone"], z["n"], z["avg_n"], z["max_n"])
                     for z in bin_zones(zone_rows, s["window_lo"], s["window_hi"])])
    con.executemany("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?)",
                    [(date, meal_name, e["kind"], e["start_ts"], e["end_ts"], e["minutes"], e["value"], e["detail"]) for e in s["events"]])
    con.executemany("INSERT INTO menu_days VALUES (?,?,?,?,?,?,?,?)",
                    [(date, meal_name, m, i, s["peak_wait"], s["rise_rate"], s["peak_queue"], s["served_est"]) for i, m in enumerate(dishes)])
    con.commit()


def rebuild_menu_stats(con):
    """menu_days 전체에서 (끼니, 메뉴)별 평균과 인기 지수를 다시 만든다. 기준(base)은 같은 끼니 안 메뉴별 평균의 중앙값 —
    끼니마다 meta menu_base_*_<meal> 에 적어 API 가 같은 값을 보여 준다 (중식 인기와 석식 인기가 섞이지 않게)"""
    all_rows = con.execute(
        "SELECT meal, menu, COUNT(*) n, AVG(peak_wait) w, AVG(rise_rate) r, AVG(peak_queue) q, MIN(date) f, MAX(date) l "
        "FROM menu_days WHERE peak_wait IS NOT NULL GROUP BY meal, menu").fetchall()
    con.execute("DELETE FROM menu_stats")
    total = 0
    for meal_name in sorted({r[0] for r in all_rows}):
        rows = [r for r in all_rows if r[0] == meal_name]
        base_w = median_or_none([r[3] for r in rows])
        base_r = median_or_none([r[4] for r in rows])
        con.executemany("INSERT INTO menu_stats VALUES (?,?,?,?,?,?,?,?,?)",
                        [(meal_name, m, n, round(w, 1) if w is not None else None, round(r, 2) if r is not None else None,
                          round(q, 1) if q is not None else None, popularity(r, w, base_r, base_w), f, l)
                         for _, m, n, w, r, q, f, l in rows])
        set_meta(con, **{f"menu_base_rise_{meal_name}": base_r, f"menu_base_wait_{meal_name}": base_w})
        total += len(rows)
    con.commit()
    return total


def backup(path):
    """WAL 에 남은 프레임까지 담기게 SQLite backup API 로 복사한다(파일 복사는 -wal 을 놓친다)"""
    bak = path.with_name(f"{path.name}.bak-{dt.datetime.now():%Y%m%d-%H%M%S}")
    with sqlite3.connect(path) as src, sqlite3.connect(bak) as dst:
        src.backup(dst)
    src.close()
    dst.close()
    return bak


# ---- 실행 --------------------------------------------------------------------------

def pick_dates(a, qcon):
    if a.date:
        return [a.date]
    if a.all:
        return list_dates(qcon)
    today = dt.date.today()
    return [(today - dt.timedelta(days=i)).isoformat() for i in reversed(range(a.days))]


def report(s, zones, meal_name):
    ev = {}
    for e in s["events"]:
        ev[e["kind"]] = ev.get(e["kind"], 0) + 1
    print(f"{s['date']} [{meal_name}]  표본 {s['n_samples']}  커버리지 {s['coverage_pct']}%  최대 대기 {s['peak_wait']}분@{(s['peak_wait_ts'] or '')[11:16]}  "
          f"처리 {s['served_est']}명  황금 {s['golden_min']}분  병목 {s['bottleneck_min']}분  구역행 {len(zones)}  이벤트 {ev}")


def main():
    ap = argparse.ArgumentParser(description="queue.db → insights.db 하루 단위 집계")
    ap.add_argument("--date", type=lambda s: dt.date.fromisoformat(s).isoformat(), help="YYYY-MM-DD 하루만")
    ap.add_argument("--days", type=int, default=2, help="오늘부터 거슬러 N일 (기본 2)")
    ap.add_argument("--all", action="store_true", help="queue.db 의 모든 날짜 (백업 후)")
    ap.add_argument("--window", choices=WINDOWS, default=ROLLUP_WINDOW)
    ap.add_argument("--source", choices=SOURCES, default=FEED_SOURCE)
    ap.add_argument("--dry-run", action="store_true", help="계산만 하고 아무것도 쓰지 않는다")
    a = ap.parse_args()

    qcon = connect_ro(DB_PATH, "samples")
    if qcon is None:
        print(f"{DB_PATH} 가 없다 - 집계할 표본이 없다")
        return 0
    dates = pick_dates(a, qcon)
    if not dates:
        print("집계할 날짜가 없다 (--all 인데 samples 가 비어 있다). 아무것도 하지 않는다")
        return 0
    meals = agg_meals(a.window)                  # [(meal, lo, hi)] — lunch 모드면 중식·석식 두 창(09-16)
    today = dt.date.today().isoformat()
    now_sec = seconds_of_day(dt.datetime.now())

    if a.dry_run:
        print(f"[dry-run] window={a.window} {[(m, f'{lo}~{hi}분') for m, lo, hi in meals]} source={a.source} 날짜 {len(dates)}개 - 파일을 만들거나 바꾸지 않는다")
        for date in dates:
            samples, zones = read_day(qcon, date)
            for meal_name, lo, hi in meals:
                report(day_summary(samples, date, lo, hi, now_sec if date == today else None), zones, meal_name)
        return 0

    if a.all and INSIGHTS_DB_PATH.exists():
        bak = backup(INSIGHTS_DB_PATH)
        print(f"백업 {bak.name}  되돌리기: cp {bak} {INSIGHTS_DB_PATH}")

    con = sqlite3.connect(INSIGHTS_DB_PATH, timeout=5)
    n_days, err, run_id = 0, None, None
    try:
        con.execute("PRAGMA journal_mode=WAL")
        migrate(con)
        check_meta(con, a.window, a.source)
        con.execute("INSERT INTO runs (started_at, args, dates) VALUES (?,?,?)",
                    (dt.datetime.now().isoformat(timespec="seconds"), " ".join(sys.argv[1:]), ",".join(dates)))
        run_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.commit()
        upsert_nutrition(con, read_meal())
        con.commit()
        for date in dates:
            samples, zones = read_day(qcon, date)
            if not samples:
                print(f"{date}  표본 없음 - 건너뜀")
                continue
            for meal_name, lo, hi in meals:
                s = day_summary(samples, date, lo, hi, now_sec if date == today else None)
                if not s["n_samples"]:                       # 그 끼니 창에 표본이 하나도 없으면 행을 만들지 않는다 (석식 없는 날 등)
                    continue
                write_day(con, s, zones, menu_for(con, date, meal_name), a.source, meal_name)
                report(s, zones, meal_name)
            n_days += 1
        print(f"menu_stats {rebuild_menu_stats(con)}개 메뉴")
    except Exception as e:                       # 실패도 runs 에 남긴다
        con.rollback()
        err = f"{type(e).__name__}: {e}"
        raise
    finally:
        if run_id is not None:
            con.execute("UPDATE runs SET finished_at=?, n_days=?, ok=?, error=? WHERE id=?",
                        (dt.datetime.now().isoformat(timespec="seconds"), n_days, int(err is None), err, run_id))
            con.commit()
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
