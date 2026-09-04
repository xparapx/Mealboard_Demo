"""프레임 소스 추상화 — picamera | webcam:N | file:경로. counter 는 어느 것이든 (프레임 BGR ndarray) 만 받는다.
프레임은 이 프로세스의 메모리에만 있고 어디에도 저장·전송되지 않는다(CLAUDE.md §2 영상 취급).

.env VIDEO_SOURCE:
  picamera          Camera Module 3 (Wide). 홈 Pi 에서는 쓰지 않는다(Plant 카메라와 배타) — 학교 Pi·업무 공간 Pi 전용
  webcam:0          개발 PC 의 USB/내장 웹캠 (OpenCV 인덱스)
  file:경로         동영상 파일. 끝나면 처음부터(무한 반복) — 개발 PC 검증용
"""
import time

import cv2


def parse_size(text, default=(1536, 864)):
    try:
        w, h = (int(v) for v in str(text).lower().split("x"))
        return w, h
    except ValueError:
        return default


class PiCamera:
    """picamera2. 'RGB888' 요청이 실제로는 BGR 순서의 배열을 준다(picamera2 의 오랜 관례) — OpenCV·YOLO 가 기대하는 순서와 같다"""

    def __init__(self, size, fps):
        from picamera2 import Picamera2                           # 시스템 apt 패키지 — venv 는 --system-site-packages 로 빌려 쓴다
        self.cam = Picamera2()
        cfg = self.cam.create_video_configuration(main={"size": size, "format": "RGB888"},
                                                  controls={"FrameRate": max(fps, 5)})
        self.cam.configure(cfg)
        self.cam.start()
        time.sleep(0.5)                                           # AE/AWB 안정

    def read(self):
        return self.cam.capture_array("main")

    def close(self):
        self.cam.stop()


class CvSource:
    """OpenCV VideoCapture — 웹캠 또는 파일. 파일은 끝나면 되감고, 파일의 자기 fps 로 속도를 맞춘다"""

    def __init__(self, target, size, fps, loop):
        self.cap = cv2.VideoCapture(target)
        if not self.cap.isOpened():
            raise RuntimeError(f"프레임 소스를 열지 못했다: {target!r}")
        if isinstance(target, int):
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
            self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.loop = loop
        native = self.cap.get(cv2.CAP_PROP_FPS) or 0
        self.period = 1 / native if loop and native > 0 else 0
        self.last = 0.0

    def read(self):
        if self.period:
            wait = self.period - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
        ok, frame = self.cap.read()
        if not ok and self.loop:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError("프레임을 읽지 못했다")
        return frame

    def close(self):
        self.cap.release()


def open_source(spec, size=(1536, 864), fps=5):
    kind, _, arg = str(spec or "picamera").partition(":")
    if kind == "picamera":
        return PiCamera(size, fps)
    if kind == "webcam":
        return CvSource(int(arg or 0), size, fps, loop=False)
    if kind == "file":
        if not arg:
            raise ValueError("VIDEO_SOURCE=file:경로 형식")
        return CvSource(arg, size, fps, loop=True)
    raise ValueError(f"VIDEO_SOURCE 는 picamera | webcam:N | file:경로 중 하나: {spec!r}")
