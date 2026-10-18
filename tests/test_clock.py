"""앱의 '지금'(app/clock.py, 10-18 심사 모드 가상 시계) — 순수 계산과 환경 변수 없는 기본 동작"""
import datetime as dt

from app import clock


def test_가상_시계는_기준_시각에서_실제_경과만큼_흐른다():
    anchor = dt.datetime(2026, 10, 14, 12, 38, 0)
    boot = dt.datetime(2026, 10, 18, 21, 0, 0)
    assert clock.shifted(anchor, boot, boot) == anchor
    assert clock.shifted(anchor, boot, boot + dt.timedelta(minutes=7, seconds=30)) == dt.datetime(2026, 10, 14, 12, 45, 30)


def test_기준이_없으면_벽시계():
    # 테스트 환경에는 DEMO_CLOCK 이 없다 — now() 는 datetime.now() 와 1초 안에서 같다
    if clock.active():
        return
    assert abs((clock.now() - dt.datetime.now()).total_seconds()) < 1
    assert clock.today() == dt.date.today()
