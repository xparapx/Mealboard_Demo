"""/api/admin/zones — GET(템플릿 + local overlay 결과) · PUT(검증 → data/zones.local.json, 백업 5개) · POST homography.
게이트를 지난 관리자만 온다. 템플릿 zones.json 은 읽기만 한다."""
from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel

from .. import audit, zones_store

router = APIRouter(prefix="/api/admin/zones")


class Pairs(BaseModel):
    pairs: list


@router.get("")
def get_zones():
    try:
        return {"state": "ok", **zones_store.read()}
    except (OSError, ValueError) as e:
        return {"state": "no_data", "reason": str(e)[:300], "doc": None, "local": zones_store.LOCAL.is_file(),
                "backups": zones_store.backups()}


@router.put("")
def put_zones(request: Request, body: dict = Body(...)):
    user = request.state.user
    try:
        doc, bak = zones_store.write(body, user["user"])
    except zones_store.Invalid as e:
        audit.log(user, "zones.put", "zones.local.json", "거부: " + "; ".join(e.errors)[:200], False, request.client.host)
        raise HTTPException(422, {"reason": "invalid", "errors": e.errors})
    except OSError as e:
        audit.log(user, "zones.put", "zones.local.json", f"쓰기 실패: {e}"[:200], False, request.client.host)
        raise HTTPException(500, {"reason": "write", "detail": str(e)[:200]})
    audit.log(user, "zones.put", "zones.local.json",
              f"zones={len(doc['zones'])} roi={'yes' if doc.get('roi') else 'no'} H={'yes' if doc.get('image_to_floor') else 'no'} bak={bak}",
              True, request.client.host)
    return {"state": "ok", "doc": doc, "backup": bak, "backups": zones_store.backups()}


@router.post("/homography")
def post_homography(body: Pairs):
    try:
        return {"state": "ok", **zones_store.homography(body.pairs)}
    except zones_store.Invalid as e:
        raise HTTPException(422, {"reason": "invalid", "errors": e.errors})
