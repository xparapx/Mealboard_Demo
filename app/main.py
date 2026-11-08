import mimetypes

from fastapi.responses import FileResponse
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from .config import BASE
from .routers import status, history, meal, positions, news, typical, insight

mimetypes.add_type("text/javascript", ".js")    # Windows 개발 PC 의 레지스트리가 .js 를 text/plain 으로 주면 모듈 로드가 막힌다

app = FastAPI(title="헤아림 (Mealboard)")
app.include_router(status.router)
app.include_router(history.router)
app.include_router(meal.router)
app.include_router(positions.router)
app.include_router(news.router)
app.include_router(typical.router)
app.include_router(insight.router)      # /api/insight/* — insights.db·reports.db 읽기 전용
# 화면과 서비스워커는 캐시하더라도 쓰기 전에 반드시 서버에 물어보게 한다.
# StaticFiles 는 Cache-Control 을 붙이지 않는데, 그러면 브라우저가 Last-Modified 로 신선도를 '추측'한다
# (경험칙: 파일이 묵은 기간의 10%). 이틀 된 index.html 은 약 5시간 동안 새로 받지 않으므로
# 배포가 브라우저에 도달하지 못한다 — v5 에서 서비스워커를 고치고도 같은 증상이 남았던 이유.
# no-cache 는 '캐시 금지'가 아니라 '쓰기 전 검사'다. ETag 가 같으면 304 라 비용은 거의 없다.
# 화면이 부르는 모듈(/js/)·스타일(/css/)도 같다 — 셸은 새것인데 모듈은 옛것이면 짝이 어긋난다.
REVALIDATE = ("/", "/index.html", "/sw.js", "/manifest.json", "/kiosk", "/kiosk.html")
REVALIDATE_PREFIX = ("/js/", "/css/")


@app.middleware("http")
async def revalidate_shell(request: Request, call_next):
    res = await call_next(request)
    path = request.url.path
    if path in REVALIDATE or path.startswith(REVALIDATE_PREFIX):
        res.headers["Cache-Control"] = "no-cache"
    return res


# 송출 화면(11-02, 제안서 P9): /kiosk 와 kiosk.* 호스트의 "/" 가 static/kiosk.html 을 낸다 — 통행로 모니터는 kiosk.kjhs-meal.com 한 주소만 외우면 된다
# (Cloudflare '게시된 애플리케이션' kiosk.kjhs-meal.com → HTTP 127.0.0.1:8100, 공개 데모 8800 도 /kiosk 가 같이 뜬다). 서비스워커 없음 — 6시간마다 스스로 새로 읽는다
KIOSK_HTML = BASE / "static" / "kiosk.html"


@app.get("/kiosk", include_in_schema=False)
def kiosk():
    return FileResponse(KIOSK_HTML, media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.middleware("http")
async def kiosk_host(request: Request, call_next):
    if request.url.path == "/" and request.headers.get("host", "").split(":")[0].startswith("kiosk."):
        return FileResponse(KIOSK_HTML, media_type="text/html", headers={"Cache-Control": "no-cache"})
    return await call_next(request)


# 정적 파일은 마지막에 mount — /api/* 가 먼저 잡히도록
app.mount("/", StaticFiles(directory=BASE / "static", html=True), name="static")
