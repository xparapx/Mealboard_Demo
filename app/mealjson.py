"""data/meal.json 읽기. fetch_neis 가 쓰고 세 곳(공개 /api/meal · 집계 rollup · 인사이트 API)이 읽는다 — 읽는 규칙은 여기 한 곳.
캐시 형식(week[] 의 assess·macro_ratio·carbon)이 바뀌면 이 파일만 고친다."""
import json

from .config import MEAL_JSON
from .insight_calc import normalize_menu


def read_meal():
    """없거나 덮어쓰는 순간에 읽혀 깨졌으면 {} — 호출자는 .get 으로 읽는다"""
    try:
        return json.loads(MEAL_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def iso_date(ymd):
    """NEIS 의 '20260824' → '2026-08-24'"""
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"


def _row(day, meal_name, d, fetched_at):
    """중식이면 week[] 항목 자체, 석식이면 그 안의 dinner 절 — 같은 모양(menu·kcal·assess·carbon)이라 한 함수로 만든다"""
    a = d.get("assess") or {}
    ratio = a.get("macro_ratio") or {}
    ok = a.get("macro_ratio_ok")
    return {"date": day, "meal": meal_name, "kcal": d.get("kcal"), "energy_pct": a.get("energy_pct"),
            "protein_pct": a.get("protein_pct"), "carb_ratio": ratio.get("carb"), "protein_ratio": ratio.get("protein"),
            "fat_ratio": ratio.get("fat"), "macro_ok": None if ok is None else int(ok), "mar": a.get("mar"),
            "kgco2e": (d.get("carbon") or {}).get("kgco2e"), "menu": d.get("menu") or [],
            "fetched_at": fetched_at}


def nutrition_rows(meal, meals=("lunch", "dinner")):
    """week[] → nutrition_days 한 행씩(dict, meal 열 포함 — 09-16 중식/석식 분리). 석식이 없는 날은 석식 행이 안 나온다.
    집계가 저장하고, 집계가 없을 때 인사이트 API 가 같은 모양으로 폴백한다"""
    rows = []
    for d in meal.get("week") or []:
        day = iso_date(d["date"])
        if "lunch" in meals:
            rows.append(_row(day, "lunch", d, meal.get("fetched_at")))
        if "dinner" in meals and d.get("dinner"):
            rows.append(_row(day, "dinner", d["dinner"], meal.get("fetched_at")))
    return rows


def menu_on(meal, date, meal_name="lunch"):
    """그날·그 끼니의 정제된 메뉴명(알레르기 번호 제거). 없으면 []"""
    for r in nutrition_rows(meal, meals=(meal_name,)):
        if r["date"] == date:
            return [m for m in (normalize_menu(x) for x in r["menu"]) if m]
    return []
