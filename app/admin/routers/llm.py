"""/api/admin/llm — AI 모델(LLM) 선택(10-20, 공모전 '모델 비종속'을 관리 화면에서).
GET: 지금 적용되는 엔진·후보(Hailo .hef, OpenAI 호환 서버의 모델)·마지막 점검 · PUT: 선택 저장(data/llm.local.json, 다음 뉴스·리포트 작업부터) ·
DELETE: .env 로 되돌리기 · POST /check: 두 과제(뉴스 요약·리포트 JSON) 점검 — 급식 창 안에는 거부(force 로 강행). 게이트를 지난 관리자만 온다."""
import datetime as dt

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ...config import LLM_BACKEND, LLM_BASE_URL, LLM_HEF, LLM_MODEL
from ... import llm_overlay
from ...lunch import meal_now
from .. import audit, llm_store

router = APIRouter(prefix="/api/admin/llm")


class Choice(BaseModel):
    backend: str
    model: str = ""
    base_url: str = ""


class CheckReq(BaseModel):
    n: int = 1
    force: bool = False


def _state():
    eff = llm_overlay.effective()
    local = llm_overlay.read()
    return {"state": "ok", "effective": eff, "env": {"backend": LLM_BACKEND, "model": LLM_MODEL, "base_url": LLM_BASE_URL, "hef": LLM_HEF},
            "local": {k: local.get(k) for k in ("backend", "model", "base_url", "updated_at", "updated_by")},
            "candidates": {"hailo": llm_store.hef_candidates(), "server": llm_store.server_candidates(eff["base_url"])},
            "last_check": local.get("last_check"), "backups": llm_store.backups()}


@router.get("")
def get_llm():
    return _state()


@router.put("")
def put_llm(request: Request, body: Choice):
    user = request.state.user
    try:
        doc, bak = llm_store.write(body.model_dump(), user)
    except llm_store.Invalid as e:
        audit.log(user, "llm.put", "llm.local.json", "거부: " + "; ".join(e.errors)[:200], False, request.client.host)
        raise HTTPException(422, {"reason": "invalid", "errors": e.errors})
    except OSError as e:
        raise HTTPException(500, {"reason": "write", "detail": str(e)[:200]})
    audit.log(user, "llm.put", "llm.local.json", f"{doc.get('backend')} {doc.get('model', '')} {doc.get('base_url', '')} bak={bak}", True, request.client.host)
    return {"state": "ok", **_state(), "backup": bak}


@router.delete("")
def delete_llm(request: Request):
    bak = llm_store.reset(request.state.user)
    audit.log(request.state.user, "llm.reset", "llm.local.json", f"bak={bak}", True, request.client.host)
    return {"state": "ok", **_state(), "backup": bak}


@router.post("/check")
async def check_llm(request: Request, body: CheckReq = Body(default=CheckReq())):
    """점검은 모델을 올려 CPU·HAT 를 쓴다 — 급식 창 안(카메라 추론 중)에는 거부. 결과 요약은 llm.local.json last_check 에"""
    user = request.state.user
    now = dt.datetime.now()
    if meal_now(now) and not body.force:
        raise HTTPException(409, {"reason": "meal_window", "detail": "급식 창 안에는 모델 점검을 하지 않는다(force 로 강행 가능)"})
    from jobs.llm import check_summary
    res = await run_in_threadpool(check_summary, max(1, min(3, body.n)))
    try:
        llm_store.write_check(res)
    except OSError:
        pass
    audit.log(user, "llm.check", res.get("model") or res.get("engine"),
              f"news {res['news']['pass']}/{res['news']['n']} report {res['report']['pass']}/{res['report']['n']} {res['news'].get('ms')}ms", res.get("ok", False), request.client.host)
    return {"state": "ok", "result": res}
