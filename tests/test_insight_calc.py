"""인사이트 판정 규칙(PLAN §2.3). 합성 표본만 쓴다 — DB 없음."""
import pytest

from app.insight_calc import (bin_samples, bin_zones, bottlenecks, coverage, day_summary, golden_bins, golden_windows,
                              insufficient_runs, median_or_none, normalize_menu, popularity, rise_rate, served_estimate,
                              typical_rate)

DATE = "2026-09-03"


def ts(minute, sec=0):
    return f"{DATE}T{minute // 60:02d}:{minute % 60:02d}:{sec:02d}"


def sample(minute, queue, rate, sec=0):
    """mock 과 같은 규칙으로 상태를 정한다: λ < 0.5 이고 줄이 있으면 산출 불가"""
    if queue > 0 and rate < 0.5:
        return {"ts": ts(minute, sec), "queue_len": queue, "rate_per_min": rate, "wait_min": None, "state": "insufficient_rate"}
    return {"ts": ts(minute, sec), "queue_len": queue, "rate_per_min": rate,
            "wait_min": round(queue / rate, 1) if queue else 0.0, "state": "ok"}


def every30s(minute_from, minute_to, queue, rate):
    """30초 간격 표본 (폴링 주기와 같다)"""
    out = []
    for m in range(minute_from, minute_to):
        out += [sample(m, queue, rate, 0), sample(m, queue, rate, 30)]
    return out


def test_구간_통계는_5분_눈금():
    s = every30s(720, 730, 10, 5.0)          # 12:00~12:10
    bins = bin_samples(s)
    assert [b["bin"] for b in bins] == [720, 725]
    assert bins[0]["n"] == 10 and bins[0]["ok_n"] == 10 and bins[0]["avg_wait"] == 2.0 and bins[0]["max_queue"] == 10


def test_구역_구간_통계는_창_밖을_버린다():
    rows = [{"ts": ts(720), "zone": "aisle", "n": 4}, {"ts": ts(721), "zone": "aisle", "n": 6},
            {"ts": ts(720), "zone": "counter", "n": 1}, {"ts": ts(480), "zone": "seating", "n": 9}]
    z = bin_zones(rows, 690, 840)
    assert z == [{"bin": 720, "zone": "aisle", "n": 2, "avg_n": 5.0, "max_n": 6},
                 {"bin": 720, "zone": "counter", "n": 1, "avg_n": 1.0, "max_n": 1}]
    assert len(bin_zones(rows)) == 3


def test_커버리지는_120초_초과분만_빈_시간으로():
    s = every30s(690, 700, 3, 4.0) + every30s(710, 840, 3, 4.0)     # 11:39:30 → 11:50:00 사이 10.5분 공백
    c = coverage(s, DATE, 690, 840)
    assert c["stale_min"] == 8.5                                    # 10.5분 - 2분(마지막 값을 보여주는 시간)
    assert c["gaps"] == [{"start_ts": ts(701, 30), "end_ts": ts(710), "minutes": 8.5}]
    assert c["coverage_pct"] == pytest.approx(100 * (1 - 8.5 / 150), abs=0.1)


def test_첫_표본_앞도_같은_유예를_두고_오늘은_지금까지만_잰다():
    s = every30s(700, 720, 3, 4.0)
    c = coverage(s, DATE, 690, 840, now_sec=720 * 60)
    assert c["stale_min"] == 8.0 and c["gaps"][0]["start_ts"] == ts(692)
    assert c["coverage_pct"] == pytest.approx(100 * (1 - 8 / 30), abs=0.1)


def test_창_밖_표본은_커버리지에_끼지_않는다():
    s = every30s(480, 510, 3, 4.0) + every30s(690, 840, 3, 4.0)      # 아침 표본은 점심 창과 무관
    c = coverage(s, DATE, 690, 840)
    assert c["coverage_pct"] == 100.0 and c["gaps"] == []


def test_표본이_없으면_창_전체가_빈_시간():
    c = coverage([], DATE, 690, 840)
    assert c["stale_min"] == 148.0 and c["coverage_pct"] == pytest.approx(1.3, abs=0.1)
    assert c["gaps"] == [{"start_ts": ts(692), "end_ts": ts(840), "minutes": 148.0}]


def test_하루_끝은_23_59_59_로_눌린다():
    s = every30s(0, 60, 3, 4.0)
    c = coverage(s, DATE, 0, 1440)
    assert c["gaps"][-1]["end_ts"] == f"{DATE}T23:59:59"


def test_처리_인원은_끊긴_동안을_세지_않는다():
    s = every30s(720, 730, 10, 6.0) + every30s(760, 770, 10, 6.0)   # 두 덩어리, 사이 30분 공백
    # 각 덩어리 19개 간격 × 30초 × 6명/분 = 57명, 공백 간격은 120초까지만 → 12명
    assert served_estimate(s) == round(57 * 2 + 6 * 2)


def test_평소_처리율은_줄이_있는_ok_표본의_중앙값():
    s = every30s(720, 725, 10, 4.0) + every30s(725, 730, 10, 8.0) + every30s(730, 740, 2, 20.0)
    assert typical_rate(s) == 6.0
    assert typical_rate(every30s(720, 730, 0, 0.0)) is None


def test_황금_구간은_5분_이상_연속일_때만():
    s = every30s(720, 724, 2, 5.0) + every30s(724, 730, 30, 5.0) + every30s(730, 740, 2, 5.0)
    g = golden_windows(s)
    assert len(g) == 1 and g[0]["start_ts"] == ts(730) and g[0]["minutes"] == 9.5 and g[0]["value"] == 0.4


def test_예보_곡선의_황금_구간은_같은_문턱():
    pts = [{"minute_of_day": m, "forecast_wait": w} for m, w in
           [(690, 1.0), (695, 2.0), (700, 3.0), (705, 8.0), (710, 2.5), (720, 2.0), (725, None), (730, 1.0)]]
    assert golden_bins(pts) == [{"start_min": 690, "end_min": 705}, {"start_min": 710, "end_min": 715},
                                {"start_min": 720, "end_min": 725}, {"start_min": 730, "end_min": 735}]
    assert golden_bins([]) == []


def test_황금_구간은_데이터_공백에서_끊긴다():
    s = every30s(720, 724, 2, 5.0) + every30s(730, 734, 2, 5.0)      # 4분 + 4분, 사이 6분 공백
    assert golden_windows(s) == []


def test_배식_중단은_병목으로_잡힌다():
    # 평소 λ 6 → 45~55분 배식 중단(mock --scenario stall 과 같은 모양): λ 가 0 으로 떨어져 산출 불가
    s = every30s(720, 745, 20, 6.0) + every30s(745, 755, 40, 0.0) + every30s(755, 780, 20, 6.0)
    b = bottlenecks(s)
    assert len(b) == 1 and b[0]["start_ts"] == ts(745) and b[0]["value"] == 40 and "평소 6.0/분" in b[0]["detail"]
    assert insufficient_runs(s)[0]["minutes"] == 9.5


def test_처리율이_평소의_절반_아래여도_병목():
    s = every30s(720, 740, 20, 6.0) + every30s(740, 745, 20, 2.0) + every30s(745, 760, 20, 6.0)
    assert [e["minutes"] for e in bottlenecks(s)] == [4.5]


def test_병목은_줄이_없으면_아니다():
    s = every30s(720, 740, 20, 6.0) + every30s(740, 745, 2, 0.1)
    assert bottlenecks(s) == []


def test_상승_속도는_이웃_구간의_기울기_최대():
    bins = [{"bin": 720, "avg_queue": 2.0}, {"bin": 725, "avg_queue": 12.0}, {"bin": 730, "avg_queue": 15.0},
            {"bin": 740, "avg_queue": 40.0}]                        # 735 가 비어 있으면 그 쌍은 건너뛴다
    assert rise_rate(bins) == 2.0
    assert rise_rate([{"bin": 720, "avg_queue": 9.0}, {"bin": 725, "avg_queue": 3.0}]) == 0.0
    assert rise_rate([]) is None


@pytest.mark.parametrize("raw, clean", [
    ("김치찌개 (1.5.6.10.13)", "김치찌개"),
    ("현미밥", "현미밥"),
    ("돈까스+소스S (1.2.5.6.10.13.15.16)", "돈까스+소스S"),
    ("우유200", "우유200"),
    ("불고기 1.5.6.", "불고기"),
    ("  *잡곡밥  ", "잡곡밥"),
])
def test_메뉴명_정제(raw, clean):
    assert normalize_menu(raw) == clean


def test_인기_지수():
    assert popularity(2.0, 6.0, 1.0, 3.0) == 200
    assert popularity(1.0, 3.0, 1.0, 3.0) == 100
    assert popularity(None, 6.0, 1.0, 3.0) == 200           # 한 항이 없으면 남은 항으로
    assert popularity(1.0, 3.0, None, None) is None
    assert median_or_none([3.0, None, 1.0, 2.0]) == 2.0 and median_or_none([None]) is None


def test_하루_요약은_창_밖_표본을_버리고_이벤트를_시각순으로():
    s = every30s(680, 690, 50, 1.0) + every30s(690, 720, 20, 6.0) + every30s(720, 730, 40, 0.0) \
        + every30s(730, 760, 20, 6.0) + every30s(770, 780, 2, 6.0)
    d = day_summary(s, DATE, 690, 840)
    assert d["n_samples"] == 160 and d["first_ts"] == ts(690)
    assert d["peak_queue"] == 40 and d["peak_wait"] == pytest.approx(3.3)
    assert d["bottleneck_min"] == 9.5 and d["insufficient_min"] == 9.5 and d["golden_min"] == 9.5
    assert [e["kind"] for e in d["events"]] == ["bottleneck", "insufficient", "stale", "golden", "stale"]
    assert d["typical_rate"] == 6.0 and d["calc_version"] == 1 and d["bins"][0]["bin"] == 690
    assert "golden" not in d and "bottlenecks" not in d          # 이벤트 하나로만 표현한다
    assert all("sec" in s for s in s[20:40])                      # 시각은 한 번만 파싱해 표본에 남긴다


def test_밀집도는_틱당_평균과_최댓값_기준_진하기():
    from app.insight_calc import density
    out = density({3: 60, 7: 30, 9: 0, 999: 5}, ticks=30, cols=5, rows=8)
    assert out == [{"i": 3, "avg": 2.0, "w": 1.0}, {"i": 7, "avg": 1.0, "w": 0.5}]     # 0 인 셀·격자 밖 셀은 뺀다
    assert density({}, 30, 5, 8) == [] and density({1: 5}, 0, 5, 8) == []
