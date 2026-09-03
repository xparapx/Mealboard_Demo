"""점심 가드 — 순수 함수. 카운팅 프로세스(vision·mock)를 급식 시간에 재시작하면 카운팅 공백이 생긴다(CLAUDE.md §5).
관리 앱은 이 함수가 True 를 돌려주면 409 lunch_guard 로 거절하고, `force:true` 로만 진행한다."""
from ..lunch import minute_of_day

GUARDED = ("mealboard-vision", "mealboard-mock")      # 재시작이 카운팅 공백을 만드는 유닛


def unit_name(unit):
    """'mealboard-vision.service' 도 'mealboard-vision' 도 같은 유닛"""
    return unit[:-8] if unit.endswith(".service") else unit


def needs_force(unit, now, lo, hi):
    """급식 창 [lo, hi) 분 안에 가드 대상 유닛을 재시작하려는가. now 는 datetime"""
    return unit_name(unit) in GUARDED and lo <= minute_of_day(now) < hi
