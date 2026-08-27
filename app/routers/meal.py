import json
from fastapi import APIRouter
from ..config import MEAL_JSON

router = APIRouter()


@router.get("/api/meal")
def meal():
    if not MEAL_JSON.exists():
        return {"state": "no_data", "message": "fetch_neis.py 가 아직 실행되지 않았습니다"}
    return json.loads(MEAL_JSON.read_text(encoding="utf-8"))
