"""리포트(PLAN §5.3) — 검증기·템플릿·LLM 폴백·reports.db 쓰기. 장치 없이 돈다(가짜 backend)."""
import json
import sqlite3

import pytest

from jobs import report, report_templates as tpl
from jobs.llm import LLMBusy, LLMUnavailable, LocalLLM, numbers, numbers_subset, parse_json_object, valid_korean


def test_숫자_집합과_부분집합():
    assert numbers("대기 12분, 1,234명, 3.0분") == {"12", "1234", "3"}
    assert numbers_subset('{"peak_wait": 12, "served": 340}', "최대 12분, 340명") and not numbers_subset("12분", "13분")


def test_한국어_검증기():
    src = '{"peak_wait": 7}'
    assert valid_korean(src, "오늘 최대 대기 7분이었습니다.")[0]
    assert valid_korean(src, "Today max wait 7 min")[1] == "hangul"
    assert valid_korean(src, "오늘 최대 대기 9분")[1] == "numbers"
    assert valid_korean(src, "한 줄\n두 줄")[1] == "format" and valid_korean(src, "https://x 참고")[1] == "format"
    assert valid_korean(src, "가" * 50, max_len=40)[1] == "length" and valid_korean(src, "")[1] == "empty"


def test_json_추출():
    assert parse_json_object('```json\n{"a": 1}\n```')["a"] == 1
    assert parse_json_object("no json") is None and parse_json_object("[1,2]") is None


def test_템플릿은_길이_스키마를_지킨다():
    p = tpl.preview({"weekday": 3, "menu": ["김치찌개", "제육볶음", "밥"], "typical": {"peak_minute": 740, "peak_wait": 9.5, "low_minute": 800, "days": 3}})
    r = tpl.recap({"menu": ["김치찌개"], "peak_wait": 6.0, "peak_wait_hm": "12:20", "peak_queue": 31, "avg_wait": 2.4, "served_est": 380, "golden_min": 25, "bottleneck_min": None, "n_samples": 500})
    for out in (p, r, tpl.preview({"weekday": 1, "menu": [], "typical": None}), tpl.recap({"menu": [], "peak_wait": None, "n_samples": 3, "coverage_pct": 4})):
        assert set(out) == {"headline", "body", "tone"} and len(out["headline"]) <= 40 and len(out["body"]) <= 120 and out["tone"] in report.TONES
    assert "12:20" in p["headline"] and "9.5" in p["body"] and p["tone"] == "busy"
    assert "380" in r["body"] and r["tone"] == "calm"


@pytest.fixture
def dbs(tmp_path):
    ins = tmp_path / "insights.db"
    con = sqlite3.connect(ins)
    con.executescript("""
    CREATE TABLE lunch_days (date TEXT PRIMARY KEY, weekday INTEGER, window_lo INTEGER, window_hi INTEGER, source TEXT, n_samples INTEGER, coverage_pct REAL,
      stale_min REAL, insufficient_min REAL, first_ts TEXT, last_ts TEXT, peak_wait REAL, peak_wait_ts TEXT, peak_queue INTEGER, peak_queue_ts TEXT, avg_wait REAL,
      served_est INTEGER, typical_rate REAL, rise_rate REAL, golden_min REAL, bottleneck_min REAL, menu_json TEXT, main_dish TEXT, calc_version INTEGER, computed_at TEXT);
    CREATE TABLE lunch_bins (date TEXT, weekday INTEGER, bin INTEGER, n INTEGER, ok_n INTEGER, insufficient_n INTEGER, avg_queue REAL, max_queue INTEGER, avg_rate REAL, avg_wait REAL, max_wait REAL);
    CREATE TABLE events (date TEXT, kind TEXT, start_ts TEXT, end_ts TEXT, minutes REAL, value REAL, detail TEXT);
    """)
    con.execute("INSERT INTO lunch_days (date, weekday, n_samples, coverage_pct, peak_wait, peak_wait_ts, peak_queue, avg_wait, served_est, golden_min, bottleneck_min, menu_json) "
                "VALUES ('2026-09-03', 4, 500, 96.4, 6.0, '2026-09-03T12:20:10', 31, 2.4, 380, 25.0, 0, ?)", (json.dumps(["김치찌개(5.6)", "제육볶음", "밥"]),))
    con.execute("INSERT INTO events VALUES ('2026-09-03','golden','2026-09-03T12:40:00','2026-09-03T13:05:00',25,2.1,'')")
    for wk in range(3):                                        # 같은 목요일 3주치 평소 곡선
        d = f"2026-08-{13 + wk * 7:02d}"
        for i, w in enumerate([1, 2, 5, 9, 7, 4, 2, 1]):
            con.execute("INSERT INTO lunch_bins VALUES (?,4,?,10,10,0,5,10,12,?,?)", (d, 700 + i * 5, w, w))
    con.commit(); con.close()
    return ins, tmp_path / "reports.db"


def test_결산은_집계_행에서_입력을_만든다(dbs):
    ins, _ = dbs
    inp = report.build_recap("2026-09-03", report.connect_ro(ins, "lunch_days"))
    assert inp["menu"] == ["김치찌개", "제육볶음", "밥"] and inp["peak_wait_hm"] == "12:20" and inp["golden_min"] == 25 and inp["events"][0]["kind"] == "golden"
    assert report.build_recap("2026-09-02", report.connect_ro(ins, "lunch_days")) is None


def test_예보는_같은_요일_곡선에서_피크를_찾는다(dbs):
    ins, _ = dbs
    meal = {"week": [{"date": "20260903", "menu": ["된장찌개(5.6)", "불고기"]}]}
    inp = report.build_preview("2026-09-03", meal, report.connect_ro(ins, "lunch_days"))
    assert inp["menu"] == ["된장찌개", "불고기"] and inp["typical"]["basis"] == "weekday" and inp["typical"]["peak_minute"] == 715 and inp["typical"]["days"] == 3


def test_LLM_없으면_템플릿_행이_쓰인다(dbs):
    ins, rep = dbs
    res, inp = report.run("recap", "2026-09-03", insights=ins, reports=rep, template_only=True, log=lambda *a: None)
    assert res["engine"] == "template" and res["reason"] == "llm_unavailable" and rep.exists()
    rows = sqlite3.connect(rep).execute("SELECT kind, for_date, engine, ok, headline FROM reports").fetchall()
    assert rows == [("recap", "2026-09-03", "template", 1, res["headline"])]
    assert report.run("recap", "2026-09-02", insights=ins, reports=rep, template_only=True, log=lambda *a: None)[0] is None


def test_dry_run_은_파일을_만들지_않는다(dbs):
    ins, rep = dbs
    res, _ = report.run("preview", "2026-09-03", insights=ins, reports=rep, meal={"week": []}, dry_run=True, template_only=True, log=lambda *a: None)
    assert res["engine"] == "template" and not rep.exists()


def fake_llm(text):
    def factory():
        return LocalLLM(hef="fake-model.hef", backend=lambda s, u, mt, t, to: text)
    return factory


def test_LLM_출력은_검증을_통과해야_hailo_행(dbs):
    ins, rep = dbs
    good = '{"headline": "김치찌개 날, 최대 대기 6분", "body": "오늘 380명이 지났고 평균 대기는 2.4분이었습니다. 여유 구간이 25분 있었습니다.", "tone": "calm"}'
    res, _ = report.run("recap", "2026-09-03", insights=ins, reports=rep, llm_factory=fake_llm(good), log=lambda *a: None)
    assert res["engine"] == "hailo" and res["model"] == "fake-model" and res["headline"].startswith("김치찌개")
    made_up = '{"headline": "최대 대기 9분", "body": "오늘 380명이 지났습니다.", "tone": "calm"}'           # 9 는 입력에 없다
    res, _ = report.run("recap", "2026-09-03", insights=ins, reports=rep, llm_factory=fake_llm(made_up), log=lambda *a: None)
    assert res["engine"] == "template" and res["reason"] == "llm_rejected:headline:numbers"
    english = '{"headline": "Kimchi day", "body": "380 students passed.", "tone": "calm"}'
    assert report.compose("recap", {"served_est": 380, "menu": []}, fake_llm(english), log=lambda *a: None)["reason"] == "llm_rejected:headline:hangul"
    assert report.compose("recap", {"menu": []}, fake_llm("not json"), log=lambda *a: None)["reason"] == "llm_rejected:schema"


def test_busy_는_재시도_뒤_템플릿(dbs):
    calls = []

    def factory():
        calls.append(1)
        raise LLMBusy("device busy")
    res = report.compose("recap", {"menu": []}, factory, busy_wait_s=0, log=lambda *a: None)
    assert res["engine"] == "template" and res["reason"] == "llm_busy" and len(calls) == report.BUSY_RETRY


def test_hef_없으면_LLMUnavailable():
    with pytest.raises(LLMUnavailable):
        with LocalLLM(hef=""):
            pass
    with pytest.raises(LLMUnavailable):
        with LocalLLM(hef="/nonexistent/model.hef"):
            pass
