"""/api/admin/whoami · services · services/{unit}/restart · jobs/{job}/run · logs/{unit} · audit
신원은 server.py 의 게이트 미들웨어가 request.state.user 에 넣는다 — 여기 오는 요청은 이미 관리자다."""
import datetime as dt

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ...config import ADMIN_PORT, ROLLUP_WINDOW
from ...lunch import bounds
from .. import audit, health, sysctl
from ..guard import needs_force

router = APIRouter(prefix="/api/admin")
LUNCH_LO, LUNCH_HI = bounds("lunch")            # 가드는 언제나 급식 창(스테이징의 all 창과 무관)


class Restart(BaseModel):
    force: bool = False


@router.get("/whoami")
def whoami(request: Request):
    u = request.state.user
    return {"state": "ok", "user": u["user"], "via": u["via"], "lockdown": request.app.state.lockdown,
            "port": ADMIN_PORT, "window": ROLLUP_WINDOW}


@router.get("/services")
def services():
    return {"state": "ok", "units": [sysctl.unit_state(u) for u in sysctl.UNITS],
            "health": health.snapshot(), "lunch": {"lo": LUNCH_LO, "hi": LUNCH_HI}}


@router.post("/services/{service}/restart")
def restart(service: str, body: Restart, request: Request):
    if service not in sysctl.RESTARTABLE:
        raise HTTPException(404, "재시작 대상이 아니다")
    now = dt.datetime.now()
    if needs_force(f"mealboard-{service}", now, LUNCH_LO, LUNCH_HI) and not body.force:
        raise HTTPException(409, {"reason": "lunch_guard", "message": "급식 시간에는 카운팅이 끊긴다 — force 로만 재시작한다"})
    rc, out, err = sysctl.restart(service)
    audit.log(request.state.user, "service.restart", service, f"force={body.force} rc={rc} {err.strip()[:200]}", rc == 0, request.client.host)
    if rc != 0:
        raise HTTPException(502, {"reason": "systemctl", "rc": rc, "stderr": err.strip()[:500]})
    return {"state": "ok", "service": service, "forced": body.force}


@router.post("/jobs/{job}/run")
def run_job(job: str, request: Request):
    if job not in sysctl.JOBS:
        raise HTTPException(404, "작업이 아니다")
    rc, out, err = sysctl.start_job(job)
    audit.log(request.state.user, "job.run", job, f"rc={rc} {err.strip()[:200]}", rc == 0, request.client.host)
    if rc != 0:
        raise HTTPException(502, {"reason": "systemctl", "rc": rc, "stderr": err.strip()[:500]})
    return {"state": "ok", "job": job}


@router.get("/logs/{unit}")
def logs(unit: str, lines: int = Query(50, ge=1, le=sysctl.MAX_LINES)):
    if unit not in sysctl.LOG_UNITS:
        raise HTTPException(404, "로그 대상이 아니다")
    rc, text = sysctl.journal(unit, lines)
    return {"state": "ok" if rc == 0 else "no_data", "unit": unit, "lines": text.splitlines()[-lines:], "reason": None if rc == 0 else text}


@router.get("/audit")
def audit_log(n: int = Query(50, ge=1, le=500)):
    return {"state": "ok", "items": audit.recent(n)}
