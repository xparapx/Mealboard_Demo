import json
from fastapi import APIRouter
from ..config import DATA

router = APIRouter()


@router.get("/api/news")
def news():
    p = DATA / "news.json"
    if not p.exists():
        return {"state": "no_data", "items": []}
    return json.loads(p.read_text(encoding="utf-8"))
