"""스트림 — 두 경로 모두 tailnet 관리자만, 저장·버퍼 없음 (CLAUDE.md §2 영상 취급·히트맵 행, PLAN §4.4).

① 메타데이터: MetaHub 가 인증된 SSE 구독자가 있을 때만 소켓을 bind 하고(POSIX AF_UNIX DGRAM RUN_DIR/meta.sock,
   Windows 개발 PC 는 UDP 127.0.0.1:META_UDP_PORT) 마지막 구독자가 떠나면 닫고 unlink 한다 — 아무도 보지 않으면
   좌표가 vision 프로세스를 떠나지 않는다. 구독당 asyncio.Queue(QUEUE_N) drop-oldest, 구독 ≤ MAX_SUBS. 프레임은 전달만 하고 남기지 않는다.
② MJPEG(opt-in): 플래그 파일(DEBUG_FLAG) 이 켜짐 계약이다. on = 파일 쓰기 + 자동 off 타이머(≤ MAX_MIN 분), off = unlink.
   vision 은 플래그가 없거나 mtime 이 10분을 넘으면 스스로 503 — 2중 안전장치. 프록시는 127.0.0.1:DEBUG_PORT/mjpeg 의 바이트를
   그대로 흘려보낸다(뷰어 1명, 디스크 접촉 없음). 관리 앱이 재시작돼도 플래그 안의 until 을 읽어 타이머를 이어간다(resume).
전부 이벤트 루프 위에서만 돈다(스레드 없음)."""
import asyncio
import datetime as dt
import json
import os
import socket
import time

from ..config import DEBUG_FLAG, DEBUG_PORT, META_UDP_PORT, RUN_DIR
from . import audit

MAX_MIN, DEFAULT_MIN = 10, 5
MAX_SUBS, QUEUE_N = 3, 5
PING_SEC = 15                               # SSE 유휴 시 주석 프레임 — 프록시 타임아웃 방지 + 끊긴 클라이언트 감지
SOCK_NAME = "meta.sock"
UPSTREAM_TIMEOUT = 3


class HubFull(Exception):
    pass


# ---------------- 플래그 파일 (순수 함수) ----------------
def clamp_minutes(m):
    """요청 분 → 1..MAX_MIN. 숫자가 아니면 기본값"""
    try:
        m = int(m)
    except (TypeError, ValueError):
        return DEFAULT_MIN
    return min(max(m, 1), MAX_MIN)


def flag_read(path=DEBUG_FLAG):
    """플래그 → {'until','by','minutes'} 또는 None. until 은 언제나 mtime+MAX_MIN 분을 넘지 못한다(vision 의 mtime 규칙과 같은 상한 —
    손으로 고친 파일이나 시계가 뒤로 간 경우에도 10분). 내용이 깨졌으면 그 상한이 곧 until 이다"""
    try:
        st = path.stat()
    except OSError:
        return None
    cap = dt.datetime.fromtimestamp(st.st_mtime) + dt.timedelta(minutes=MAX_MIN)
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        until = min(dt.datetime.fromisoformat(d["until"]), cap)
        return {"until": until, "by": d.get("by"), "minutes": d.get("minutes")}
    except (OSError, ValueError, KeyError, TypeError):
        return {"until": cap, "by": None, "minutes": None}


def flag_write(path, until, by, minutes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"until": until.isoformat(timespec="seconds"), "by": by, "minutes": minutes}), encoding="utf-8")


def flag_remove(path=DEBUG_FLAG):
    try:
        path.unlink()
        return True
    except OSError:
        return False


def remaining_s(flag, now=None):
    if not flag:
        return 0
    return max(0, int((flag["until"] - (now or dt.datetime.now())).total_seconds()))


def parse_head(head):
    """HTTP 응답 머리(bytes, 빈 줄까지) → (status, {소문자 헤더: 값})"""
    lines = head.decode("latin-1").split("\r\n")
    parts = lines[0].split(" ", 2)
    try:
        status = int(parts[1])
    except (IndexError, ValueError):
        status = 0
    headers = {}
    for ln in lines[1:]:
        if ":" in ln:
            k, v = ln.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return status, headers


# ---------------- 메타데이터 허브 ----------------
class MetaHub(asyncio.DatagramProtocol):
    def __init__(self, run_dir=RUN_DIR, port=META_UDP_PORT):
        self.subs = set()
        self.transport = None
        self.path = run_dir / SOCK_NAME
        self.port = port
        self.unix = hasattr(socket, "AF_UNIX")
        self.frames = 0
        self.last = None                        # 마지막 데이터그램 시각(monotonic)
        self._lock = None                       # bind 직렬화 — 루프가 있을 때 만든다

    # -- DatagramProtocol
    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.frames += 1
        self.last = time.monotonic()
        for q in self.subs:
            if q.full():
                q.get_nowait()                  # drop-oldest: 느린 구독자가 최신 프레임을 놓치지 않게
            q.put_nowait(data)

    def error_received(self, exc):
        pass

    def connection_lost(self, exc):
        self.transport = None

    # -- 구독
    @property
    def endpoint(self):
        return str(self.path) if self.unix else f"udp://127.0.0.1:{self.port}"

    def info(self):
        return {"bound": self.transport is not None, "endpoint": self.endpoint, "subscribers": len(self.subs),
                "frames": self.frames, "last_age_s": None if self.last is None else round(time.monotonic() - self.last, 1)}

    async def subscribe(self):
        if len(self.subs) >= MAX_SUBS:
            raise HubFull()
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:                  # 동시에 온 두 구독이 둘 다 bind 하지 않게(두 번째는 첫 소켓을 unlink 해 버린다)
            if self.transport is None:
                await self._bind()
        q = asyncio.Queue(QUEUE_N)
        self.subs.add(q)
        return q

    def unsubscribe(self, q):
        self.subs.discard(q)
        if not self.subs:
            self._unbind()

    def kick(self):
        """lockdown 등 — 모든 구독자에게 종료 신호(None). 큐가 차 있으면 하나 비우고 넣는다"""
        for q in list(self.subs):
            if q.full():
                q.get_nowait()
            q.put_nowait(None)

    async def _bind(self):
        """소켓은 직접 bind 해서 sock= 으로 넘긴다 — uvloop(Pi 의 uvicorn[standard]) 는 AF_UNIX 경로를 local_addr 로 받지 않는다"""
        loop = asyncio.get_running_loop()
        if self.unix:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self.path.unlink()
            except OSError:
                pass
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            try:
                sock.bind(str(self.path))
                os.chmod(self.path, 0o660)      # 같은 사용자·그룹(mealboard)만 — vision·mock 이 같은 계정으로 돈다
            except OSError:
                sock.close()
                raise
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.bind(("127.0.0.1", self.port))
            except OSError:
                sock.close()
                raise
        sock.setblocking(False)
        try:
            await loop.create_datagram_endpoint(lambda: self, sock=sock)
        except Exception:
            sock.close()
            raise

    def _unbind(self):
        if self.transport is not None:
            self.transport.close()
            self.transport = None
        if self.unix:
            try:
                self.path.unlink()
            except OSError:
                pass


# ---------------- 스트림 상태 (플래그 + 타이머 + 뷰어) ----------------
class StreamState:
    def __init__(self, flag=DEBUG_FLAG, port=DEBUG_PORT, hub=None):
        self.flag = flag
        self.port = port
        self.hub = hub or MetaHub()
        self.timer = None
        self.viewers = 0
        self.off = asyncio.Event()              # off/autooff/lockdown → 릴레이가 다음 1초 안에 끊는다(파일을 폴링하지 않고)

    def current(self):
        return flag_read(self.flag)

    def is_on(self):
        return remaining_s(self.current()) > 0

    def state(self):
        f = self.current()
        rem = remaining_s(f)
        return {"state": "on" if rem > 0 else "off", "until": f["until"].isoformat(timespec="seconds") if f and rem > 0 else None,
                "remaining_s": rem, "minutes": f["minutes"] if f else None, "by": f["by"] if f else None,
                "viewers": self.viewers, "meta": self.hub.info(), "debug_port": self.port, "max_minutes": MAX_MIN}

    async def resume(self):
        """관리 앱 시작 때: 남은 플래그가 있으면 타이머를 이어가고, 이미 지났으면 지운다"""
        f = self.current()
        if not f:
            return
        rem = remaining_s(f)
        if rem <= 0:
            flag_remove(self.flag)
            audit.log(None, "stream.autooff", "mjpeg", "시작 시 만료된 플래그 제거", True)
        else:
            self._arm(rem)

    def turn_on(self, minutes, user, ip=None):
        m = clamp_minutes(minutes)
        until = dt.datetime.now() + dt.timedelta(minutes=m)
        flag_write(self.flag, until, (user or {}).get("user"), m)
        self.off.clear()
        self._arm(m * 60)
        audit.log(user, "stream.on", "mjpeg", f"{m}분 · until {until.isoformat(timespec='seconds')}", True, ip)
        return self.state()

    def turn_off(self, user, ip=None, reason="off"):
        self._disarm()
        self.off.set()
        if flag_remove(self.flag):
            audit.log(user, "stream." + reason, "mjpeg", f"viewers={self.viewers}", True, ip)
        return self.state()

    # -- MJPEG 뷰어 자리(1명). claim 은 await 전에 동기적으로 — 요청 두 개가 연결 대기 사이에 같이 통과하지 않는다
    def claim(self):
        if self.viewers >= 1:
            return False
        self.viewers += 1
        return True

    def release(self):
        self.viewers = max(0, self.viewers - 1)

    def _arm(self, seconds):
        self._disarm()
        self.timer = asyncio.get_running_loop().call_later(seconds, self._auto_off)

    def _disarm(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None

    def _auto_off(self):
        self.timer = None
        self.off.set()
        if flag_remove(self.flag):
            audit.log(None, "stream.autooff", "mjpeg", f"viewers={self.viewers}", True)

    def shutdown(self):
        self._disarm()
        self.hub.kick()
        self.hub._unbind()

    # -- MJPEG 프록시
    async def open_upstream(self):
        """→ (status, headers, reader, writer). 연결 실패는 OSError/TimeoutError 로 올라간다"""
        reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", self.port), UPSTREAM_TIMEOUT)
        try:
            writer.write(b"GET /mjpeg HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            await writer.drain()
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), UPSTREAM_TIMEOUT + 2)
        except (OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError):
            writer.close()
            raise OSError("upstream head")
        status, headers = parse_head(head)
        return status, headers, reader, writer

    async def relay(self, reader, writer, user, ip=None):
        """upstream 바이트를 그대로 넘긴다. 자리(claim)는 라우터가 미리 잡았고 여기서 돌려준다. off·autooff·lockdown 이면 1초 안에 끊는다 —
        upstream 이 멈춘 채 열려 있어도(read 가 돌아오지 않아도) 마찬가지(wait_for 1초). 아무것도 남기지 않는다"""
        t0, nbytes, check = time.monotonic(), 0, time.monotonic()
        audit.log(user, "stream.view", "mjpeg", "open", True, ip)
        try:
            while not self.off.is_set():
                try:
                    chunk = await asyncio.wait_for(reader.read(65536), 1.0)
                except asyncio.TimeoutError:
                    chunk = None                                     # 조용한 upstream — 플래그만 다시 본다
                if chunk == b"":
                    break
                if chunk:
                    nbytes += len(chunk)
                    yield chunk
                if time.monotonic() - check > 1:
                    check = time.monotonic()
                    if not self.is_on():
                        break
        finally:
            self.release()
            writer.close()
            audit.log(user, "stream.view", "mjpeg", f"close · {round(time.monotonic() - t0)}초 · {nbytes // 1024}KB", True, ip)
