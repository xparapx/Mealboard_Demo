"""점심 가드 — 급식 시간에 카운팅 프로세스를 재시작하려면 force 가 필요하다."""
import datetime as dt

from app.admin.guard import needs_force, unit_name


def test_유닛_이름_정규화():
    assert unit_name("mealboard-vision.service") == "mealboard-vision"
    assert unit_name("mealboard-api") == "mealboard-api"


def test_급식_시간의_vision_mock_재시작은_force_필요():
    noon = dt.datetime(2026, 9, 3, 12, 15)
    assert needs_force("mealboard-vision", noon, 690, 840)
    assert needs_force("mealboard-mock.service", noon, 690, 840)


def test_api_재시작은_언제나_자유():
    assert not needs_force("mealboard-api", dt.datetime(2026, 9, 3, 12, 15), 690, 840)


def test_창_밖이면_자유_끝은_열린_구간():
    assert not needs_force("mealboard-vision", dt.datetime(2026, 9, 3, 11, 29), 690, 840)
    assert not needs_force("mealboard-vision", dt.datetime(2026, 9, 3, 14, 0), 690, 840)
    assert needs_force("mealboard-vision", dt.datetime(2026, 9, 3, 11, 30), 690, 840)
