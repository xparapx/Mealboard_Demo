"""수집 시간창(09-04 운영 규칙, 09-11 시작 앞당김, 09-16 끝 조정) — 3학년 점심 11:20~12:30 · 1·2학년 점심 12:30~13:40 · 석식 17:00~18:10.
설정 파일도 시계도 없이 도는 순수 로직(vision/schedule.py)과, 그 위의 /api/status feed 판정을 본다."""
import datetime as dt

import pytest

from vision.schedule import DEFAULT_TEXT, MealWindow, current, describe, next_after, parse_windows

W = parse_windows(DEFAULT_TEXT)


def test_기본_문자열은_세_창():
    assert W == [MealWindow(680, 750, "3학년 점심"), MealWindow(750, 820, "1·2학년 점심"), MealWindow(1020, 1090, "석식")]


def test_정렬과_라벨_기본값():
    w = parse_windows("17:30-18:30; 11:30-12:30 ;")
    assert [x.lo for x in w] == [690, 1050] and w[0].label == "급식"


def test_빈_문자열은_창_없음():
    assert parse_windows("") == [] and parse_windows(None) == []


@pytest.mark.parametrize("bad", ["11:30", "11:30~12:30", "12:30-11:30 역순", "25:00-26:00", "11:30-12:30 a;12:00-13:00 겹침"])
def test_잘못된_창은_예외(bad):
    with pytest.raises(ValueError):
        parse_windows(bad)


def test_지금_열린_창():
    assert current(W, 680).label == "3학년 점심" and current(W, 679) is None   # 11:20 부터
    assert current(W, 749).label == "3학년 점심"
    assert current(W, 750).label == "1·2학년 점심"        # 끝은 열린 구간 — 12:30 은 다음 창
    assert current(W, 820) is None                        # 13:40 부터 창 밖(09-16 끝 조정)
    assert current(W, 1089).label == "석식" and current(W, 1090) is None
    assert current([], 700) is None


def test_다음_창():
    assert next_after(W, 9 * 60) == (W[0], 0)              # 아침 → 오늘 3학년 점심
    assert next_after(W, 720) == (W[1], 0)                 # 3학년 점심 중 → 1·2학년 점심(지금 창은 세지 않는다)
    assert next_after(W, 820) == (W[2], 0)                 # 점심 끝 → 석식
    assert next_after(W, 1050) == (W[0], 1)                # 석식 중(17:30) → 내일 3학년 점심
    assert next_after(W, 23 * 60) == (W[0], 1)
    assert next_after([], 700) is None


def test_describe():
    assert describe(W[2]) == {"label": "석식", "lo": 1020, "hi": 1090}
    assert describe(None) is None


def test_should_record_창_안_vision_만():
    from vision.schedule import should_record
    w = W[0]
    assert should_record(w, "vision") is True
    assert should_record(None, "vision") is False        # 창 밖: 아무 행도 쓰지 않는다(더미 없음, 09-11)
    assert should_record(w, "mock") is False             # mock 출처면 카메라 노드는 쓰지 않는다 — 더미는 mock 유닛의 몫
    assert should_record(None, "mock") is False


def test_status_feed_판정():
    from app.routers.status import feed
    lunch = dt.datetime(2026, 9, 4, 12, 0)
    night = dt.datetime(2026, 9, 4, 20, 0)
    assert feed(lunch, "ok", source="vision")["live"] is True
    assert feed(lunch, "no_data", source="vision")["live"] is False      # 창 안이어도 표본이 끊기면 실측이 아니다
    assert feed(lunch, "ok", source="mock")["live"] is False             # 스테이징 mock 은 창 안이어도 더미
    f = feed(night, "ok", source="vision")
    assert f["live"] is False and f["now"] is None
    assert f["next"]["label"] == "3학년 점심" and f["next"]["days"] == 3 and f["next"]["lo"] == 680   # 2026-09-04 는 금요일 → 월요일(3일 뒤)


def test_다음_급식_날은_주말과_급식_없는_날을_건너뛴다():
    """09-11: 토요일 밤 '내일 11:20' 은 틀리다. NEIS 캐시 범위에서는 캐시가 진실, 밖에서는 주말만 건너뛴다"""
    from app.lunch import next_meal_day
    sat = dt.datetime(2026, 9, 12, 20, 0)                                   # 토
    assert next_meal_day(sat) == (dt.date(2026, 9, 14), 2)                   # 월
    week = ["20260914", "20260916", "20260917", "20260918"]                  # 화(9/15) 급식 없음(공휴일 가정)
    assert next_meal_day(dt.datetime(2026, 9, 15, 9, 0), week) == (dt.date(2026, 9, 16), 1)     # 화(공휴일) → 수. 날짜 단위 판단(시각은 next_with_day 가 본다)
    assert next_meal_day(dt.datetime(2026, 9, 14, 9, 0), week) == (dt.date(2026, 9, 14), 0)
    assert next_meal_day(dt.datetime(2026, 9, 19, 9, 0), week) == (dt.date(2026, 9, 21), 2)   # 캐시 밖 → 다음 월요일


def test_status_next_는_날짜와_요일을_준다(monkeypatch):
    from app.routers import status
    monkeypatch.setattr(status, "read_meal", lambda: {"week": [{"date": "20260914", "menu": ["x"]}]})
    n = status.next_with_day(dt.datetime(2026, 9, 12, 20, 0))                # 토요일 밤
    assert n["date"] == "2026-09-14" and n["weekday"] == "월" and n["days"] == 2 and n["label"] == "3학년 점심"
    n = status.next_with_day(dt.datetime(2026, 9, 14, 12, 0))                # 월 점심 중 → 같은 날 다음 창
    assert n["date"] == "2026-09-14" and n["days"] == 0 and n["label"] == "1·2학년 점심"
