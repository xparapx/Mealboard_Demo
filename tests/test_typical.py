"""/api/typical 의 시간창 계산. DB 없이 도는 순수 로직만 본다."""
import datetime as dt

from app.routers.typical import window


def test_정오_두시간창():
    assert window(dt.datetime(2026, 8, 26, 12, 30), 120) == (630, 750)


def test_자정_직후에는_0_으로_자른다():
    # 00:30 에서 두 시간을 되짚으면 전날로 넘어간다. 급식은 한낮이므로 넘기지 않고 자른다
    assert window(dt.datetime(2026, 8, 26, 0, 30), 120) == (0, 30)


def test_창의_길이는_요청한_분과_같다():
    lo, hi = window(dt.datetime(2026, 8, 26, 13, 5), 90)
    assert hi - lo == 90
