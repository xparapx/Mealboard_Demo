"""앱의 '지금' — 한 곳에서만 읽는다(10-18, 심사위원 구동 경로 N3).

평소에는 벽시계(datetime.now) 그대로다. `.env DEMO_CLOCK=2026-10-14T12:38:00` 처럼 기준 시각을 주면 **프로세스가 뜬 순간을 그 시각으로 보고**
거기서부터 실제 시간이 흐른다 — 심사위원이 토요일 밤에 켜도 화면은 '수요일 12:38, 1·2학년 점심' 한가운데에서 시작하고 초가 간다.
가상 시계는 공개 API(status·history·typical·insight·positions)·집계(rollup)·리포트(report)·더미 피드(mock_feed·demo)가 함께 쓴다.
화면(core.js)은 /api/status 의 now 로 서버 시계와의 차이를 맞춘다. 카메라 노드(vision)는 이 모듈을 쓰지 않는다 — 실측은 언제나 벽시계."""
import datetime as dt
import os

DEMO_CLOCK = os.getenv("DEMO_CLOCK", "").strip()
_ANCHOR = dt.datetime.fromisoformat(DEMO_CLOCK) if DEMO_CLOCK else None
_BOOT = dt.datetime.now()


def active():
    """가상 시계인가"""
    return _ANCHOR is not None


def now():
    """지금(로컬, tz 없음). 가상 시계면 기준 시각 + 프로세스가 뜬 뒤 흐른 시간"""
    if _ANCHOR is None:
        return dt.datetime.now()
    return _ANCHOR + (dt.datetime.now() - _BOOT)


def today():
    return now().date()


def rewind():
    """가상 시계를 기준 시각으로 되감는다(상시 공개 데모 — jobs/demo.py --loop). 벽시계 모드에서는 아무 일도 없다"""
    global _BOOT
    if _ANCHOR is not None:
        _BOOT = dt.datetime.now()


def shifted(anchor, boot, real_now):
    """순수 계산(테스트용): 기준 anchor · 부팅 boot · 실제 real_now → 가상 지금"""
    return anchor + (real_now - boot)
