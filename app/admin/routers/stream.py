"""/api/admin/stream/{state | on | off | meta | mjpeg} — 게이트를 지난 관리자만 온다 (server.py).
meta 는 SSE(text/event-stream), mjpeg 는 vision 디버그 서버(127.0.0.1:DEBUG_PORT)의 multipart 바이트를 그대로 중계한다."""
import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import audit
from ..stream import DEFAULT_MIN, HubFull, MAX_MIN, PING_SEC

router = APIRouter(prefix="/api/admin/stream")
NO_STORE = {"Cache-Control": "no-store"}


class On(BaseModel):
    minutes: int = Field(DEFAULT_MIN, ge=1, le=MAX_MIN)


def _st(request):
    return request.app.state.stream


# on/off 는 async 여야 한다 — 자동 off 타이머(call_later)가 이벤트 루프 위에서 잡혀야 하므로(동기 def 는 스레드풀에서 돈다)
@router.get("/state")
async def state(request: Request):
    return _st(request).state()


@router.post("/on")
async def on(body: On, request: Request):
    return _st(request).turn_on(body.minutes, request.state.user, request.client.host)


@router.post("/off")
async def off(request: Request):
    return _st(request).turn_off(request.state.user, request.client.host)


@router.get("/meta")
async def meta(request: Request):
    st = _st(request)
    user, ip = request.state.user, request.client.host
    try:
        q = await st.hub.subscribe()
    except HubFull:
        raise HTTPException(429, {"reason": "subscribers", "max": 3})
    except (OSError, TypeError, ValueError) as e:            # 소켓을 열지 못했다(경로·권한·루프 구현) — 500 이 아니라 503 로 말한다
        raise HTTPException(503, {"reason": "bind", "detail": str(e)[:200]})
    audit.log(user, "stream.meta", "subscribe", st.hub.endpoint, True, ip)

    async def gen():
        frames = 0
        try:
            yield b"event: hello\ndata: " + json.dumps(st.hub.info()).encode() + b"\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), PING_SEC)
                except asyncio.TimeoutError:
                    yield b": ping\n\n"          # 유휴 — 쓰기가 실패하면 여기서 끝난다(끊긴 클라이언트)
                    continue
                if data is None:                 # kick (lockdown·종료)
                    yield b"event: bye\ndata: {}\n\n"
                    break
                frames += 1
                yield b"data: " + data + b"\n\n"
        finally:
            st.hub.unsubscribe(q)
            audit.log(user, "stream.meta", "unsubscribe", f"frames={frames}", True, ip)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/mjpeg")
async def mjpeg(request: Request):
    st = _st(request)
    if not st.is_on():
        raise HTTPException(409, {"reason": "off", "message": "stream/on 으로 먼저 켠다"})
    if st.viewers >= 1:
        raise HTTPException(409, {"reason": "viewer_busy", "message": "다른 뷰어가 보는 중 (1명)"})
    try:
        status, headers, reader, writer = await st.open_upstream()
    except (OSError, asyncio.TimeoutError):
        audit.log(request.state.user, "stream.view", "mjpeg", "vision_absent", False, request.client.host)
        raise HTTPException(502, {"reason": "vision_absent", "port": st.port})
    if status != 200:
        writer.close()
        raise HTTPException(502, {"reason": "upstream", "status": status})
    ctype = headers.get("content-type", "multipart/x-mixed-replace; boundary=frame")
    return StreamingResponse(st.relay(reader, writer, request.state.user, request.client.host), media_type=ctype, headers=NO_STORE)
