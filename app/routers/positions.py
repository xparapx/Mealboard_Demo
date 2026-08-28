import datetime as dt
import json
from fastapi import APIRouter
from ..config import DATA

router = APIRouter()
POSITIONS = DATA / "positions.json"
STALE_SEC = 120   # status.py 와 같은 규칙: 이 시간 넘게 새 파일이 없으면 '데이터 없음'


@router.get("/api/positions")
def positions():
    """익명 위치 마커의 순간 상태. 파일 하나를 덮어쓸 뿐 이력은 어디에도 남지 않는다 (CLAUDE.md §2)"""
    empty = {"state": "no_data", "updated_at": None, "stale": False, "n": 0, "points": []}
    if not POSITIONS.exists():
        return empty
    try:
        p = json.loads(POSITIONS.read_text(encoding="utf-8"))
    except ValueError:                       # 덮어쓰는 순간에 읽혔을 때 — 다음 폴링에서 정상
        return empty
    age = (dt.datetime.now() - dt.datetime.fromisoformat(p["updated_at"])).total_seconds()
    if age > STALE_SEC:
        return {**empty, "updated_at": p["updated_at"], "stale": True}
    return {"state": "ok", "updated_at": p["updated_at"], "stale": False, "n": p["n"], "points": p["points"]}
