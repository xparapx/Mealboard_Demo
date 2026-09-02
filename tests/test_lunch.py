"""급식 시간창·5분 구간. 설정 파일도 시계도 없이 도는 순수 로직만 본다."""
import datetime as dt

import pytest

from app.lunch import BUCKET_MIN, bin_of, bounds, in_window, lunch_bounds, minute_of_day, parse_hhmm, seconds_of_day


def test_시각_문자열을_분으로():
    assert parse_hhmm("11:30") == 690
    assert parse_hhmm(" 14:00 ") == 840
    assert parse_hhmm("0:05") == 5


@pytest.mark.parametrize("bad", ["1130", "25:00", "12:60", "", "오후 1시"])
def test_잘못된_시각은_예외(bad):
    with pytest.raises(ValueError):
        parse_hhmm(bad)


def test_급식_시간창은_반열린_구간():
    assert lunch_bounds("11:30", "14:00") == (690, 840)


def test_끝이_시작보다_앞서면_예외():
    with pytest.raises(ValueError):
        lunch_bounds("14:00", "11:30")


def test_all_창은_하루_전체():
    assert bounds("all") == (0, 1440)


def test_lunch_창은_env_값을_따른다():
    lo, hi = bounds("lunch")
    assert lunch_bounds() == (lo, hi) and lo < hi


def test_미지의_창_이름은_예외():
    with pytest.raises(ValueError):
        bounds("dinner")


def test_자정부터_초_소수까지():
    assert seconds_of_day(dt.datetime(2026, 9, 3, 12, 3, 30, 500000)) == 43410.5
    assert seconds_of_day("2026-09-03T12:03:30.500") == 43410.5


def test_구간의_시작_분으로_내림():
    assert BUCKET_MIN == 5
    assert bin_of("2026-09-03T12:03:59") == 720
    assert bin_of("2026-09-03T12:05:00") == 725
    assert minute_of_day("2026-09-03T00:00:59") == 0


def test_창_안팎_판정은_끝을_포함하지_않는다():
    assert in_window("2026-09-03T11:30:00", 690, 840)
    assert in_window("2026-09-03T13:59:59", 690, 840)
    assert not in_window("2026-09-03T14:00:00", 690, 840)
