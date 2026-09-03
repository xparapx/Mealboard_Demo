"""리포트 생성 → data/reports.db. 이 파일이 reports.db 의 유일한 writer 다 (CLAUDE.md §2). `/api/insight/text` 가 읽는다.

두 종류(PLAN §5.3):
  preview  05:45 — 오늘 메뉴(meal.json)·요일·평소 곡선(insights.db lunch_bins, 같은 요일 최근 4주 → 최근 전체) → 언제 붐비는지
  recap    14:20 — 오늘 집계 행(insights.db lunch_days, rollup 14:10 이후)·이벤트 → 결산 한 줄
엔진: 로컬 LLM(jobs/llm.py) → 출력 JSON {headline≤40, body≤120, tone} 검증(한글·숫자 부분집합·길이) 통과 시 engine=hailo,
      미설치·busy(60초×3 재시도)·검증 실패 → jobs/report_templates.py 규칙 문장 engine=template. 어느 쪽이든 행 하나.
입력은 숫자·정제된 메뉴명뿐(프레임·좌표 없음). insights.db·queue.db 는 읽기 전용 연결.

실행:  uv run python -m jobs.report --kind preview|recap|auto [--date YYYY-MM-DD] [--dry-run] [--template]
       auto = 12:00 전이면 preview, 뒤면 recap. systemd: mealboard-report.timer 05:45·14:20 → --kind auto
"""
import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
import time

from app.config import INSIGHTS_DB_PATH, REPORTS_DB_PATH, LLM_REPORT
from app.insight_calc import normalize_menu
from app.insights_db import connect_ro
from app.lunch import weekday_of
from app.mealjson import menu_on, read_meal
from jobs import report_templates as tpl
from jobs.llm import LLMBusy, LLMUnavailable, LocalLLM, parse_json_object, valid_korean

KINDS = ("preview", "recap")
TONES = ("calm", "busy", "info")
MENU_RE = re.compile(r"[^가-힣0-9A-Za-z ()&·,]")
BUSY_RETRY, BUSY_WAIT_S = 3, 60
SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, for_date TEXT NOT NULL,
  engine TEXT NOT NULL, model TEXT, ok INTEGER NOT NULL, ms INTEGER, headline TEXT, body TEXT, tone TEXT, input_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_reports_date ON reports (for_date, kind);
"""
SYSTEM = ("너는 학교 급식실 안내판의 짧은 글을 쓰는 작성자다. 입력 JSON 의 숫자와 메뉴명만 사용하고 입력에 없는 사실·숫자는 절대 만들지 않는다. "
          "학생에게 말하듯 존댓말로, 한국어로만 쓴다. 출력은 JSON 하나뿐: {\"headline\": 40자 이하 한 줄, \"body\": 120자 이하 두세 문장, "
          "\"tone\": \"calm\"|\"busy\"|\"info\"}. 다른 말·코드펜스·개행 없이 JSON 만 출력한다.")


# ---------------- 입력 만들기 (읽기 전용) ----------------
def clean_menu(items, n=6):
    """정제된 메뉴명만 — 알레르기 번호 제거(normalize_menu), 허용 문자 밖 제거, 20자 이하, 최대 n개"""
    out = []
    for m in items or []:
        s = MENU_RE.sub("", normalize_menu(str(m)) or "").strip()[:20]
        if s:
            out.append(s)
    return out[:n]


def typical_for(icon, date, weeks=4):
    """같은 요일 최근 weeks 주의 lunch_bins 평균 → {peak_minute, peak_wait, low_minute, days, basis}. 표본 없으면 None"""
    if icon is None:
        return None
    wd = weekday_of(date)
    since = (dt.date.fromisoformat(date) - dt.timedelta(weeks=weeks)).isoformat()
    for basis, sql, args in (
        ("weekday", "SELECT bin, AVG(avg_wait) w, COUNT(DISTINCT date) d FROM lunch_bins WHERE weekday = ? AND date >= ? AND date < ? AND avg_wait IS NOT NULL GROUP BY bin", (wd, since, date)),
        ("recent", "SELECT bin, AVG(avg_wait) w, COUNT(DISTINCT date) d FROM lunch_bins WHERE date < ? AND avg_wait IS NOT NULL GROUP BY bin", (date,)),
    ):
        rows = icon.execute(sql, args).fetchall()
        if len(rows) >= 6:
            peak = max(rows, key=lambda r: r["w"])
            low = min(rows, key=lambda r: r["w"])
            return {"basis": basis, "days": max(r["d"] for r in rows), "peak_minute": int(peak["bin"]), "peak_wait": round(peak["w"], 1),
                    "low_minute": int(low["bin"]) if low["w"] < peak["w"] else None}
    return None


def build_preview(date, meal, icon):
    return {"kind": "preview", "date": date, "weekday": weekday_of(date), "menu": clean_menu(menu_on(meal, date)),
            "typical": typical_for(icon, date)}


def build_recap(date, icon):
    """그날의 집계 행이 있어야 결산이 있다. 없으면 None"""
    if icon is None:
        return None
    row = icon.execute("SELECT * FROM lunch_days WHERE date = ?", (date,)).fetchone()
    if row is None:
        return None
    ev = icon.execute("SELECT kind, minutes, value FROM events WHERE date = ? AND kind IN ('golden','bottleneck') ORDER BY start_ts", (date,)).fetchall()
    menu = clean_menu(json.loads(row["menu_json"]) if row["menu_json"] else [])
    hmv = (row["peak_wait_ts"] or "")[11:16] or None
    return {"kind": "recap", "date": date, "weekday": row["weekday"], "menu": menu, "n_samples": row["n_samples"],
            "coverage_pct": None if row["coverage_pct"] is None else round(row["coverage_pct"]),
            "peak_wait": row["peak_wait"], "peak_wait_hm": hmv, "peak_queue": row["peak_queue"],
            "avg_wait": row["avg_wait"], "served_est": row["served_est"],
            "golden_min": None if not row["golden_min"] else round(row["golden_min"]),
            "bottleneck_min": None if not row["bottleneck_min"] else round(row["bottleneck_min"]),
            "events": [{"kind": e["kind"], "minutes": round(e["minutes"] or 0), "value": e["value"]} for e in ev][:6]}


# ---------------- 문장 만들기 ----------------
def validate_output(inp, out):
    """LLM 출력 dict → (ok, reason). 스키마·길이·tone·한글·숫자 부분집합(입력 JSON 전체 기준)"""
    if not isinstance(out, dict) or set(out) - {"headline", "body", "tone"} or not all(k in out for k in ("headline", "body", "tone")):
        return False, "schema"
    if out["tone"] not in TONES:
        return False, "tone"
    # 숫자 출처는 측정값·메뉴명뿐 — 날짜(2026-09-03 → 9)·요일 번호는 빼야 지어낸 '9분' 이 통과하지 못한다
    src = json.dumps({k: v for k, v in inp.items() if k not in ("date", "kind", "weekday")}, ensure_ascii=False)
    for key, n in (("headline", 40), ("body", 120)):
        ok, why = valid_korean(src, out[key], max_len=n)
        if not ok:
            return False, f"{key}:{why}"
    return True, "ok"


def compose(kind, inp, llm_factory=None, busy_wait_s=BUSY_WAIT_S, log=print):
    """→ {engine, model, ok, ms, headline, body, tone, reason}. llm_factory() 가 LocalLLM 컨텍스트 매니저를 준다(테스트는 가짜)"""
    if llm_factory is None and not LLM_REPORT:                     # 09-04: 실장치 경로는 .env LLM_REPORT=1 일 때만 (테스트의 가짜 factory 는 게이트 밖)
        out = tpl.render(kind, inp)
        return {"engine": "template", "model": None, "ok": True, "ms": None, **out, "reason": "llm_disabled"}
    factory = llm_factory or LocalLLM
    for attempt in range(1, BUSY_RETRY + 1):
        try:
            with factory() as m:
                raw = m.complete(SYSTEM, json.dumps(inp, ensure_ascii=False), max_tokens=200)
                out = parse_json_object(raw)
                ok, why = validate_output(inp, out)
                if ok:
                    return {"engine": "hailo", "model": m.model, "ok": True, "ms": getattr(m, "last_ms", None), **out, "reason": "ok"}
                log(f"LLM 출력 거부({why}) → 템플릿")
                reason = f"llm_rejected:{why}"
                break
        except LLMBusy as e:
            log(f"LLM busy ({attempt}/{BUSY_RETRY}): {e}")
            reason = "llm_busy"
            if attempt < BUSY_RETRY:
                time.sleep(busy_wait_s)
        except LLMUnavailable as e:
            log(f"LLM 없음 → 템플릿: {e}")
            reason = "llm_unavailable"
            break
        except Exception as e:                                    # 장치 예외 어떤 것도 리포트를 막지 않는다
            log(f"LLM 오류 → 템플릿: {type(e).__name__}: {e}")
            reason = "llm_error"
            break
    out = tpl.render(kind, inp)
    return {"engine": "template", "model": None, "ok": True, "ms": None, **out, "reason": reason}


# ---------------- 쓰기 ----------------
def connect_rw(path=REPORTS_DB_PATH):
    con = sqlite3.connect(path, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def write(con, kind, date, res, inp):
    con.execute("INSERT INTO reports (ts, kind, for_date, engine, model, ok, ms, headline, body, tone, input_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (dt.datetime.now().isoformat(timespec="seconds"), kind, date, res["engine"], res["model"], int(res["ok"]), res["ms"],
                 res["headline"], res["body"], res["tone"], json.dumps(inp, ensure_ascii=False)))
    con.commit()


def run(kind, date, insights=INSIGHTS_DB_PATH, reports=REPORTS_DB_PATH, meal=None, dry_run=False, template_only=False, llm_factory=None,
        busy_wait_s=BUSY_WAIT_S, log=print):
    """→ (res, inp) 또는 (None, reason). 파일은 dry_run 이 아닐 때만 만든다"""
    icon = connect_ro(insights, "lunch_days")
    try:
        inp = build_preview(date, meal if meal is not None else read_meal(), icon) if kind == "preview" else build_recap(date, icon)
    finally:
        if icon is not None:
            icon.close()
    if inp is None:
        return None, f"{date} 의 집계 행이 없다 — rollup 이 먼저다"
    factory = llm_factory
    if template_only:
        def factory():
            raise LLMUnavailable("--template")
    res = compose(kind, inp, factory, busy_wait_s=busy_wait_s, log=log)
    if not dry_run:
        con = connect_rw(reports)
        try:
            write(con, kind, date, res, inp)
        finally:
            con.close()
    return res, inp


def main():
    ap = argparse.ArgumentParser(description="리포트 생성 → reports.db")
    ap.add_argument("--kind", choices=KINDS + ("auto",), default="auto")
    ap.add_argument("--date", type=lambda s: dt.date.fromisoformat(s).isoformat(), default=dt.date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true", help="계산만, 아무것도 쓰지 않는다")
    ap.add_argument("--template", action="store_true", help="LLM 을 건너뛰고 규칙 문장만")
    a = ap.parse_args()
    kind = a.kind if a.kind != "auto" else ("preview" if dt.datetime.now().hour < 12 else "recap")
    res, inp = run(kind, a.date, dry_run=a.dry_run, template_only=a.template)
    if res is None:
        print(f"건너뜀: {inp}")
        return 0
    print(f"{kind} {a.date} engine={res['engine']} ({res['reason']}){' [dry-run]' if a.dry_run else ''}")
    print(f"  {res['headline']}\n  {res['body']}  [{res['tone']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
