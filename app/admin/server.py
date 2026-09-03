"""관리 앱 — 별도 프로세스(ADMIN_PORT 8101, 127.0.0.1). 공개 라우터도 그대로 싣는다(관리자는 같은 대시보드 + 관리 화면을 본다).
밖으로는 `tailscale serve --https=8443 http://127.0.0.1:8101` 로만 — tailnet 안에서만 닿고, Tailscale 이 요청마다 붙이는
Tailscale-User-Login 헤더를 허용목록과 대조한다. SSH 터널 경로는 로컬 키. Funnel 헤더가 보이면 무조건 거부 (PLAN §4.1, fail-closed).

실행: uv run uvicorn app.admin.server:app --host 127.0.0.1 --port 8101
"""
import asyncio
import contextlib
import mimetypes

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import ADMIN_LOCAL_KEY, ADMIN_PORT, ADMIN_USERS, BASE
from ..main import REVALIDATE, REVALIDATE_PREFIX
from ..routers import history, insight, meal, news, positions, status, typical
from . import audit, sysctl, watchdog
from .auth import COOKIE, identify, parse_users
from .routers import system

mimetypes.add_type("text/javascript", ".js")
USERS = parse_users(ADMIN_USERS)
GATED = ("/api/admin/", "/admin-ui/")
WATCH_EVERY = 60


async def _watch(app):
    """60초마다 serve status 를 읽어 관리 포트가 Funnel 에 물렸으면 lockdown. 명령이 없는 기기(개발 PC)에서는 아무것도 바꾸지 않는다"""
    while True:
        try:
            rc, out, _ = await asyncio.to_thread(sysctl.run, ("tailscale", "serve", "status", "--json"), True)
            if rc == 0:
                bad = watchdog.exposed(out, ADMIN_PORT)
                if bad and not app.state.lockdown:
                    app.state.lockdown = True
                    audit.log(None, "lockdown.on", "watchdog", f"관리 포트 {ADMIN_PORT} 가 Funnel 에 노출됨", True)
                elif not bad and app.state.lockdown:
                    app.state.lockdown = False
                    audit.log(None, "lockdown.off", "watchdog", "노출 해소", True)
        except Exception as e:                       # 워치독은 죽지 않는다
            print("watchdog", e)
        await asyncio.sleep(WATCH_EVERY)


@contextlib.asynccontextmanager
async def lifespan(app):
    app.state.lockdown = False
    task = asyncio.create_task(_watch(app))
    yield
    task.cancel()


def create_app():
    app = FastAPI(title="Mealboard admin", lifespan=lifespan)
    for r in (status, history, meal, positions, news, typical, insight):
        app.include_router(r.router)
    app.include_router(system.router)

    @app.middleware("http")
    async def gate(request: Request, call_next):
        path = request.url.path
        if path.startswith(GATED):
            ident, why = identify(request.headers, request.cookies, request.query_params, USERS, ADMIN_LOCAL_KEY, request.app.state.lockdown)
            if ident is None:
                return JSONResponse({"state": "forbidden", "reason": why}, status_code=403)
            if request.method in ("POST", "PUT", "DELETE", "PATCH"):     # CSRF: JSON 본문만, 교차 사이트 거부, CORS 헤더 없음
                if not request.headers.get("content-type", "").startswith("application/json"):
                    return JSONResponse({"state": "forbidden", "reason": "json_only"}, status_code=415)
                sfs = request.headers.get("sec-fetch-site")
                if sfs and sfs not in ("same-origin", "none"):
                    return JSONResponse({"state": "forbidden", "reason": "cross_site"}, status_code=403)
            request.state.user = ident
        res = await call_next(request)
        if path in REVALIDATE or path.startswith(REVALIDATE_PREFIX) or path.startswith("/admin-ui/"):
            res.headers["Cache-Control"] = "no-cache"
        if path == "/api/admin/whoami" and "key" in request.query_params and getattr(request.state, "user", {}).get("via") == "local":
            # SSH 터널 경로: 첫 방문의 ?key= 를 HttpOnly 쿠키로 옮겨 이후 요청·화면 스크립트가 키를 다시 들고 다니지 않게
            res.set_cookie(COOKIE, request.query_params["key"], httponly=True, samesite="strict", max_age=12 * 3600)
        return res

    app.mount("/admin-ui", StaticFiles(directory=BASE / "app" / "admin" / "static"), name="admin-ui")   # 관리 UI 는 공개 static 에 두지 않는다
    app.mount("/", StaticFiles(directory=BASE / "static", html=True), name="static")
    return app


app = create_app()
