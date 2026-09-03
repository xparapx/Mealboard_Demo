from fastapi import APIRouter
from ..mealjson import read_meal

router = APIRouter()


@router.get("/api/meal")
def meal():
    m = read_meal()
    if not m:
        return {"state": "no_data", "message": "fetch_neis.py 가 아직 실행되지 않았습니다"}
    return m
