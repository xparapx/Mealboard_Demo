"""수집 시간창(09-04 운영 규칙) — 3학년 점심 11:30~12:30 · 1·2학년 점심 12:30~13:30 · 석식 17:30~18:30.
설정 파일도 시계도 없이 도는 순수 로직(vision/schedule.py)과, 그 위의 /api/status feed 판정을 본다."""
import datetime as dt

import pytest

from vision.schedule import DEFAULT_TEXT, MealWindow, current, describe, next_after, parse_windows

W = parse_windows(DEFAULT_TEXT)


def test_기본_문자열은_세_창():
    assert W == [MealWindow(690, 750, "3학년 점심"), MealWindow(750, 810, "1·2학년 점심"), MealWindow(1050, 1110, "석식")]


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
    assert current(W, 690).label == "3학년 점심"
    assert current(W, 749).label == "3학년 점심"
    assert current(W, 750).label == "1·2학년 점심"        # 끝은 열린 구간 — 12:30 은 다음 창
    assert current(W, 810) is None
    assert current(W, 1109).label == "석식" and current(W, 1110) is None
    assert current([], 700) is None


def test_다음_창():
    assert next_after(W, 9 * 60) == (W[0], 0)              # 아침 → 오늘 3학년 점심
    assert next_after(W, 720) == (W[1], 0)                 # 3학년 점심 중 → 1·2학년 점심(지금 창은 세지 않는다)
    assert next_after(W, 810) == (W[2], 0)                 # 점심 끝 → 석식
    assert next_after(W, 1050) == (W[0], 1)                # 석식 중 → 내일 3학년 점심
    assert next_after(W, 23 * 60) == (W[0], 1)
    assert next_after([], 700) is None


def test_describe():
    assert describe(W[2]) == {"label": "석식", "lo": 1050, "hi": 1110}
    assert describe(None) is None


def test_status_feed_판정():
    from app.routers.status import feed
    lunch = dt.datetime(2026, 9, 4, 12, 0)
    night = dt.datetime(2026, 9, 4, 20, 0)
    assert feed(lunch, "ok", source="vision")["live"] is True
    assert feed(lunch, "no_data", source="vision")["live"] is False      # 창 안이어도 표본이 끊기면 실측이 아니다
    assert feed(lunch, "ok", source="mock")["live"] is False             # 스테이징 mock 은 창 안이어도 더미
    f = feed(night, "ok", source="vision")
    assert f["live"] is False and f["now"] is None
    assert f["next"]["label"] == "3학년 점심" and f["next"]["days"] == 1 and f["next"]["lo"] == 690
