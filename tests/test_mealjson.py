"""meal.json 캐시 읽기 — 집계와 인사이트 API 가 같은 모양의 행을 보는지."""
from app.mealjson import iso_date, menu_on, nutrition_rows

MEAL = {"fetched_at": "2026-08-24T05:40:00", "week": [
    {"date": "20260824", "menu": ["현미밥", "김치찌개 (1.5.6.10.13)", "*우유 (2)"], "kcal": 1094.1,
     "assess": {"energy_pct": 122, "protein_pct": 192, "macro_ratio": {"carb": 55, "protein": 15, "fat": 29},
                "macro_ratio_ok": True, "mar": 97}, "carbon": {"kgco2e": 1.52}},
    {"date": "20260825", "menu": [], "kcal": None, "assess": {}, "carbon": {}},
]}


def test_날짜_형식():
    assert iso_date("20260824") == "2026-08-24"


def test_영양_행은_집계_테이블_모양():
    rows = nutrition_rows(MEAL)
    assert [r["date"] for r in rows] == ["2026-08-24", "2026-08-25"]
    r = rows[0]
    assert (r["kcal"], r["energy_pct"], r["carb_ratio"], r["macro_ok"], r["mar"], r["kgco2e"]) == (1094.1, 122, 55, 1, 97, 1.52)
    assert r["fetched_at"] == "2026-08-24T05:40:00" and r["menu"][1] == "김치찌개 (1.5.6.10.13)"
    assert rows[1]["macro_ok"] is None and rows[1]["kgco2e"] is None


def test_그날_메뉴는_정제된_이름():
    assert menu_on(MEAL, "2026-08-24") == ["현미밥", "김치찌개", "우유"]
    assert menu_on(MEAL, "2026-08-26") == []
    assert menu_on({}, "2026-08-24") == []
