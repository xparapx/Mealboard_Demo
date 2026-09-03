"""메타데이터 발신 — vision(counter)·mock 이 프레임마다 dict 하나를 관리 앱의 소켓에 던진다. 저장·버퍼 없음, 실패 무시 (PLAN §4.4).
관리 앱은 인증된 구독자가 있을 때만 소켓을 bind 하므로, 아무도 보지 않으면 sendto 가 실패할 뿐이고 좌표는 이 프로세스를 떠나지 않는다.
POSIX: AF_UNIX DGRAM RUN_DIR/meta.sock. AF_UNIX 가 없는 개발 PC(Windows): UDP 127.0.0.1:META_UDP_PORT.
한 프레임이 데이터그램 하나 — MAX_BYTES 를 넘는 프레임은 보내지 않는다(잘린 JSON 을 흘리지 않기 위해)."""
import json
import socket

from app.config import META_UDP_PORT, RUN_DIR

MAX_BYTES = 60_000
SOCK_NAME = "meta.sock"


def encode(event):
    """dict → 데이터그램 bytes. 너무 크면 None"""
    data = json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return data if len(data) <= MAX_BYTES else None


class MetaSender:
    def __init__(self, run_dir=RUN_DIR, port=META_UDP_PORT):
        self.unix = hasattr(socket, "AF_UNIX")
        self.target = str(run_dir / SOCK_NAME) if self.unix else ("127.0.0.1", port)
        self.sock = socket.socket(socket.AF_UNIX if self.unix else socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.sent = self.dropped = 0

    def send(self, event):
        """→ True 면 소켓에 들어갔다(구독자가 있다). 수신자가 없으면 False — 오류가 아니다"""
        data = encode(event)
        if data is None:
            self.dropped += 1
            return False
        try:
            self.sock.sendto(data, self.target)
            self.sent += 1
            return True
        except OSError:                     # ENOENT·ECONNREFUSED·EAGAIN — 아무도 듣지 않는다
            self.dropped += 1
            return False

    def close(self):
        self.sock.close()
