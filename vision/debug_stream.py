"""디버그 MJPEG — 카운트 프로세스 안의 127.0.0.1:DEBUG_PORT 서버(CLAUDE.md §2 디버그 뷰, PLAN §4.4).
켜짐 계약은 플래그 파일 DEBUG_FLAG(관리 앱이 만들고 지운다). /mjpeg 는 플래그가 없거나 mtime 이 MAX_AGE 를 넘으면 503 + 플래그 삭제(2중 안전장치).
프레임은 주석(bbox·ID·ROI·λ선±완충띠·HUD)을 얹은 JPEG 로 메모리에서만 오간다 — 디스크 접촉 없음. 클라이언트가 없으면 인코딩 비용 0 (wanted() 가 False).
관리 앱이 유일한 클라이언트다(tailnet 안에서만 중계, 뷰어 1명, ≤10분, 감사 기록)."""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

MAX_AGE = 600           # 플래그 mtime 이 이보다 오래되면 꺼진 것으로 본다(관리 앱의 상한과 같은 10분)
OUT_WIDTH = 960
JPEG_Q = 70
STREAM_FPS = 5


class DebugStream:
    def __init__(self, port, flag):
        self.port, self.flag = port, flag
        self.cond = threading.Condition()
        self.jpeg, self.seq = None, 0
        self.viewers = 0
        self._flag_at, self._flag_ok = 0.0, False
        self.server = None

    # -- 플래그 (1초에 한 번만 stat)
    def wanted(self):
        now = time.monotonic()
        if now - self._flag_at >= 1:
            self._flag_at = now
            self._flag_ok = self._check()
        return self._flag_ok

    def _check(self):
        try:
            st = os.stat(self.flag)
        except OSError:
            return False
        if time.time() - st.st_mtime > MAX_AGE:
            try:
                os.unlink(self.flag)                  # vision 쪽 안전장치 — 관리 앱이 죽어도 10분 뒤 스스로 끈다
            except OSError:
                pass
            return False
        return True

    # -- 프레임
    def publish(self, jpeg):
        with self.cond:
            self.jpeg, self.seq = jpeg, self.seq + 1
            self.cond.notify_all()

    def wait_frame(self, seen, timeout=1.0):
        with self.cond:
            if self.seq == seen:
                self.cond.wait(timeout)
            return self.jpeg, self.seq

    # -- 서버
    def start(self):
        stream = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *a):            # 저널을 어지럽히지 않는다
                pass

            def do_GET(self):
                if self.path.startswith("/health"):
                    body = json.dumps({"viewers": stream.viewers, "seq": stream.seq}).encode()
                    self.send_response(200); self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
                    return
                if not self.path.startswith("/mjpeg"):
                    self.send_error(404); return
                if not stream._check():
                    self.send_error(503, "debug flag off"); return
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                stream.viewers += 1
                seen, check = 0, time.monotonic()
                try:
                    while True:
                        jpeg, seen2 = stream.wait_frame(seen)
                        if jpeg is not None and seen2 != seen:
                            seen = seen2
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpeg))
                            self.wfile.write(jpeg); self.wfile.write(b"\r\n"); self.wfile.flush()
                        if time.monotonic() - check > 1:
                            check = time.monotonic()
                            if not stream._check():
                                break
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    stream.viewers -= 1

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True, name="mjpeg").start()
        return self

    def stop(self):
        if self.server:
            self.server.shutdown()


def annotate(frame, tracks, roi_px, lam, buffer, hud):
    """주석을 얹고 OUT_WIDTH 로 줄여 JPEG bytes 로. tracks = [{id, xyxy(px), foot(px), in_roi}], roi_px = 픽셀 폴리곤 또는 None,
    lam = (a, b) 픽셀 λ선 또는 None. 원본 배열은 건드리지 않는다"""
    img = frame.copy()
    if roi_px:
        cv2.polylines(img, [np.array([[int(x), int(y)] for x, y in roi_px], dtype="int32")], True, (255, 200, 60), 2)
    if lam:
        (ax, ay), (bx, by) = lam
        cv2.line(img, (int(ax), int(ay)), (int(bx), int(by)), (60, 90, 255), 3)
        if buffer:
            L = max(1e-6, ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5)
            nx, ny = -(by - ay) / L * buffer, (bx - ax) / L * buffer
            for s in (1, -1):
                cv2.line(img, (int(ax + s * nx), int(ay + s * ny)), (int(bx + s * nx), int(by + s * ny)), (60, 90, 255), 1)
    for t in tracks:
        x1, y1, x2, y2 = (int(v) for v in t["xyxy"])
        color = (60, 220, 120) if t["in_roi"] else (200, 200, 200)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.circle(img, (int(t["foot"][0]), int(t["foot"][1])), 5, (0, 215, 255), -1)
        cv2.putText(img, str(t["id"]), (x1, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    cv2.rectangle(img, (0, 0), (img.shape[1], 28), (30, 30, 30), -1)
    cv2.putText(img, hud, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (240, 240, 240), 1)
    h, w = img.shape[:2]
    if w > OUT_WIDTH:
        img = cv2.resize(img, (OUT_WIDTH, int(h * OUT_WIDTH / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_Q])
    return buf.tobytes() if ok else None
