"""카메라 카운팅 노드 — 로드맵 ④ 진입점.  실행: uv run python -m vision.counter  (systemd: mealboard-vision.service, mock 과 Conflicts)

한 프로세스가 카메라를 쥐고(배타 자원) 세 가지를 한다:
  ① 사람 검출·추적(YOLO + ByteTrack, 사람 클래스만) → ROI 안 인원(L)·λ선 통과율(λ) → 예상 대기(W=L/λ) 를 10초마다 queue.db 에 — 숫자만
  ② 관리 앱 메타데이터 스트림(bbox·ID·바닥 좌표, vision/meta.py — 구독자가 있을 때만 소켓에 들어간다)
  ③ 디버그 MJPEG(127.0.0.1:DEBUG_PORT, vision/debug_stream.py — 플래그 파일이 있을 때만 인코딩)

수집 시간창(09-04 운영 규칙, app.lunch.MEALS): 창 안에서만 실측을 기록한다. 창 밖에서는 아무 행도 쓰지 않는다(09-11 사용자 결정 — 옛 더미 곡선 제거;
표본이 끊기면 /api/status 는 120초 뒤 no_data, 화면은 '지금은 급식 시간이 아닙니다 · 다음 창' 안내). 창 밖 추론은 관리자가 실사·메타를 보고 있을 때만
돌린다(초점·ROI·보정은 급식 시간과 무관해야 하므로). 아무도 안 보면 IDLE_FPS 로 프레임만 버린다.
.env FEED_SOURCE 는 출처 표기 스위치다: vision 일 때만 이 노드가 기록한다(vision/schedule.should_record). mock 이면 더미는 mock 유닛의 몫이라
이 노드는 아무것도 쓰지 않는다(두 유닛은 Conflicts 로 배타) — 실측 숫자가 '더미' 띠 아래 섞여 나가지 않게(09-04 사용자 지적).
창이 열리는 순간 트랙 기억·λ 이동합을 비운다.

프레임은 이 프로세스 메모리에만 있다. 디스크에 쓰지 않고, 밖으로는 MJPEG(관리 앱 중계, tailnet 전용) 뿐이다(CLAUDE.md §2 영상 취급).
zones.json + zones.local.json 은 mtime 이 바뀌면 2초 안에 다시 읽는다(관리 앱 편집기 저장 → 재시작 없이 반영). 호모그래피(image_to_floor)가 아직 없으면
바닥 좌표·구역·타일·positions 는 건너뛰고 L·λ 만 기록한다(ROI 가 없으면 L = 화면 안 전원)."""
import datetime as dt
import os
import time

from app.config import (DEBUG_FLAG, DEBUG_PORT, FEED_SOURCE, RATE_WINDOW_SEC, VIDEO_SOURCE, VISION_CONF, VISION_FPS, VISION_IMGSZ, VISION_SIZE,
                        YOLO_WEIGHTS, ZONES_JSON)
from app.db import connect
from app.lunch import meal_now
from vision.counting import DwellTracker, LineCounter, MedianWindow, RateWindow, foot_of_bbox
from vision.debug_stream import DebugStream, annotate
from vision.meta import MetaSender
from vision.record import write_positions, write_sample
from vision.schedule import should_record
from vision.source import open_source, parse_size
from vision.waittime import estimate_wait
from vision.zones import LOCAL_NAME, load_zones, point_in_polygon, project, zone_of

SAMPLE_SEC = 10         # 표본 주기 (mock 의 TICK 과 같다)
POS_SEC = 5             # positions.json 갱신 주기 (09-16: 평면도 마커를 화면 5초 폴링에 맞춰 — DB 표본보다 잦아도 파일 하나 덮어쓰기뿐)
RELOAD_SEC = 2          # zones 파일 mtime 확인 주기
IDLE_FPS = 1            # 창 밖 + 보는 사람 없음: 카메라만 살려 두는 속도
PERSON = 0              # COCO class


class Zones:
    """zones.json(+local) 을 mtime 으로 다시 읽는다. ROI(이미지 정규화 폴리곤)·λ선·완충띠·호모그래피를 픽셀 단위로 준비해 둔다"""

    def __init__(self, path, img_w, img_h):
        self.path, self.local = path, path.with_name(LOCAL_NAME)
        self.w, self.h = img_w, img_h
        self.stamp, self.at = None, 0.0
        self.doc, self.zones, self.roi, self.h_img2floor, self.counter, self.buffer = None, [], None, None, None, 20
        self.reload(force=True)

    def _stamp(self):
        s = []
        for p in (self.path, self.local):
            try:
                s.append(os.stat(p).st_mtime_ns)
            except OSError:
                s.append(None)
        return tuple(s)

    def reload(self, force=False):
        now = time.monotonic()
        if not force and now - self.at < RELOAD_SEC:
            return False
        self.at = now
        st = self._stamp()
        if st == self.stamp and not force:
            return False
        self.stamp = st
        try:
            doc = load_zones(self.path)
        except (OSError, ValueError) as e:
            print(f"구역 정의를 읽지 못했다 - 이전 정의로 계속한다: {e}")
            return False
        self.doc, self.zones = doc, doc["zones"]
        self.h_img2floor = doc.get("image_to_floor")
        self.buffer = doc.get("buffer_px") or 20
        roi = doc.get("roi")
        self.roi = roi
        self.counter = None
        if roi:
            i, j = roi["lambda_edge"]
            a, b = self.px(roi["polygon"][i]), self.px(roi["polygon"][j])
            self.counter = LineCounter(a, b, roi["out_dir"], self.buffer)
        print(f"구역 정의 읽음  zones={[z['id'] for z in self.zones]}  roi={'있음' if roi else '없음'}  "
              f"호모그래피={'있음' if self.h_img2floor else '없음(바닥 좌표·구역·positions 건너뜀)'}")
        return True

    def px(self, p):
        return p[0] * self.w, p[1] * self.h

    def roi_px(self):
        return [self.px(p) for p in self.roi["polygon"]] if self.roi else None

    def lam_px(self):
        return (self.counter.a, self.counter.b) if self.counter else None

    def in_roi(self, u, v):
        return True if not self.roi else point_in_polygon(u, v, self.roi["polygon"])

    def floor(self, u, v):
        if not self.h_img2floor:
            return None
        try:
            x, y = project(self.h_img2floor, u, v)
        except ValueError:
            return None
        return round(min(max(x, 0.0), 1.0), 3), round(min(max(y, 0.0), 1.0), 3)


def main():
    size = parse_size(VISION_SIZE)
    print(f"vision 시작  source={VIDEO_SOURCE}  size={size[0]}x{size[1]}  fps={VISION_FPS}  imgsz={VISION_IMGSZ}  weights={YOLO_WEIGHTS}")
    from ultralytics import YOLO                                  # 무거운 import 는 설정 출력 뒤에
    model = YOLO(YOLO_WEIGHTS)
    src = open_source(VIDEO_SOURCE, size, VISION_FPS)
    frame = src.read()
    img_h, img_w = frame.shape[:2]
    zones = Zones(ZONES_JSON, img_w, img_h)
    stream = DebugStream(DEBUG_PORT, DEBUG_FLAG).start()
    sender = MetaSender()
    con = connect()
    rate = RateWindow(RATE_WINDOW_SEC)
    dwell = DwellTracker()                                        # 자동 실측·보정(09-16 B안) — ROI 진입→λ선 통과 체류시간
    qmed = MedianWindow(25)                                       # L 평활(09-17): 검출이 한두 프레임 끊겨도 0 으로 꺼지지 않게
    wmed = MedianWindow(90)                                       # 공표 대기 평활(09-17): 깜빡임 대신 추세만 — 원시값은 raw 로 그대로 남는다
    last_raw = None                                               # 직전 표본의 원시 예측(분) — 진입자의 '진입 시점 예측' 으로 기억
    win, last_sample, last_pos, frame_id, infer_ms = None, 0.0, 0.0, 0, 0.0
    meta_alive = 0.0                                              # 마지막으로 메타 구독자가 있었던 시각(단조)
    period = 1 / VISION_FPS
    real = FEED_SOURCE == "vision"                                # False 면 이 노드는 아무것도 쓰지 않는다(더미는 mock 유닛의 몫)
    print(f"카메라 {img_w}x{img_h}  MJPEG 127.0.0.1:{DEBUG_PORT}/mjpeg (플래그 {DEBUG_FLAG})  "
          f"기록={'실측(창 안만, 창 밖은 기록 없음)' if real else '없음(FEED_SOURCE=mock — mock 유닛이 더미를 쓴다)'}")

    while True:
        t0 = time.monotonic()
        now = dt.datetime.now()
        cur = meal_now(now)
        if cur != win:                                            # 창이 열리거나 닫힘
            win = cur
            rate.reset()
            dwell.reset()                                         # 창이 바뀌면 실측·보정도 처음부터
            qmed.reset()
            wmed.reset()
            last_raw = None
            if zones.counter:
                zones.counter.reset()
            print("--- " + (f"수집 창 열림: {win.label} - {'실측 기록' if real else '기록 없음(FEED_SOURCE=mock)'}" if win else "수집 창 닫힘 - 기록 없음, 추론은 관리자가 볼 때만") + " ---")
        zones.reload()
        viewing = stream.wanted() or (t0 - meta_alive < 3)
        infer = (win is not None and real) or viewing

        if not infer:                                             # 아무도 안 보고 창 밖: 카메라만 살려 둔다, 아무것도 쓰지 않는다
            frame = src.read()
            if sender.send({"frame_id": frame_id, "ts": now.isoformat(timespec="milliseconds"), "fps": IDLE_FPS, "infer_ms": 0,
                            "img_w": img_w, "img_h": img_h, "source": "vision", "model": "idle", "tracks": [], "crossings": [],
                            "zone_counts": {}, "roi_count": 0, "rate_per_min": 0, "wait_min": None, "state": "idle"}):
                meta_alive = time.monotonic()                     # 구독자가 나타났다 → 다음 프레임부터 추론
            time.sleep(max(0, 1 / IDLE_FPS - (time.monotonic() - t0)))
            continue

        frame = src.read()
        frame_id += 1
        ti = time.monotonic()
        res = model.track(frame, imgsz=VISION_IMGSZ, conf=VISION_CONF, classes=[PERSON], persist=True,
                          tracker="bytetrack.yaml", verbose=False)[0]
        infer_ms = (time.monotonic() - ti) * 1000
        boxes = res.boxes
        ids = boxes.id.int().tolist() if boxes is not None and boxes.id is not None else []
        xyxy = boxes.xyxy.tolist() if boxes is not None else []
        tracks, crossings, pts, served = [], [], [], 0
        ts = now.isoformat(timespec="milliseconds")
        for k, box in enumerate(xyxy):
            tid = ids[k] if k < len(ids) else -1
            fx, fy = foot_of_bbox(*box)
            u, v = fx / img_w, fy / img_h
            in_roi = zones.in_roi(u, v)
            fl = zones.floor(u, v)
            if fl:
                pts.append({"x": fl[0], "y": fl[1]})
            if tid >= 0:
                dwell.observe(tid, in_roi, t0, last_raw)          # ROI 에 처음 보인 순간 = 줄 진입(그때의 예측을 함께 기억)
            if zones.counter and tid >= 0:
                c = zones.counter.update(tid, (fx, fy))
                if c > 0:
                    served += 1; crossings.append({"id": tid, "dir": "out", "ts": ts})
                    dwell.crossed(tid, t0)                        # 배식대 통과 — 실제 대기시간 실측 이벤트
                elif c < 0:
                    crossings.append({"id": tid, "dir": "in", "ts": ts})
            tracks.append({"id": tid, "bbox_norm": [round(box[0] / img_w, 3), round(box[1] / img_h, 3), round(box[2] / img_w, 3), round(box[3] / img_h, 3)],
                           "foot_xy_norm": [round(u, 3), round(v, 3)], "floor_xy_norm": list(fl) if fl else None,
                           "in_roi": in_roi, "zone": zone_of(fl[0], fl[1], zones.zones) if fl else None,
                           "xyxy": box, "foot": (fx, fy)})
        if zones.counter:
            zones.counter.forget(ids)
            dwell.forget(ids)
        rate.add(t0, served)
        lam = rate.per_min(t0)
        inst = sum(1 for t in tracks if t["in_roi"])              # 이 프레임의 순간 L — 평활 재료로만
        qmed.add(t0, inst)
        qm = qmed.median(t0)
        queue = int(round(qm)) if qm is not None else inst        # 공표 L = 25초 중앙값(09-17 평활)
        raw, state = estimate_wait(queue, lam)
        ds = dwell.stats(t0)                                      # {n, measured_min, k} — 이동 창 요약(개인 값은 저장 안 함)
        last_raw = raw
        wnow = round(raw * ds["k"], 1) if raw is not None and ds["k"] else raw   # 자동 보정: 원시 × K(실측/예측 중앙값, 0.5~3.0)
        if state == "ok":
            wmed.add(t0, wnow)
        wm = wmed.median(t0) if state == "ok" else None
        wait = round(wm, 1) if wm is not None else wnow           # 공표 대기 = 90초 중앙값(09-17 평활) — 원시는 raw 열에 그대로
        zone_counts = {}
        for t in tracks:
            if t["zone"]:
                zone_counts[t["zone"]] = zone_counts.get(t["zone"], 0) + 1

        event = {"frame_id": frame_id, "ts": ts, "fps": VISION_FPS, "infer_ms": round(infer_ms, 1), "img_w": img_w, "img_h": img_h,
                 "source": "vision", "model": os.path.basename(YOLO_WEIGHTS),
                 "tracks": [{k: v for k, v in t.items() if k not in ("xyxy", "foot")} for t in tracks], "crossings": crossings,
                 "zone_counts": zone_counts, "roi_count": queue, "rate_per_min": round(lam, 2), "wait_min": wait, "state": state}
        if sender.send(event):
            meta_alive = time.monotonic()
        if stream.wanted():
            tag = win.label if win else "closed"
            hud = f"{tag}  L={queue}  lambda={lam:.1f}/min  W={wait if wait is not None else '-'}  {state}  infer {infer_ms:.0f}ms  tracks {len(tracks)}"
            jpeg = annotate(frame, tracks, zones.roi_px(), zones.lam_px(), zones.buffer, hud)
            if jpeg:
                stream.publish(jpeg)

        if t0 - last_pos >= POS_SEC and zones.h_img2floor and should_record(win, FEED_SOURCE):
            last_pos = t0                                         # DB 표본(10초)과 별개로 마커 파일만 5초마다 — write_sample 도 쓰지만 겹쳐도 덮어쓰기뿐
            write_positions(ts, queue, pts)
        if t0 - last_sample >= SAMPLE_SEC:
            last_sample = t0
            if should_record(win, FEED_SOURCE):                   # 실측 — 숫자(과 바닥 좌표의 순간 상태)만
                write_sample(con, ts, {"queue": queue, "rate": round(lam, 2), "wait": wait, "state": state,
                                       "raw": raw, "measured": ds["measured_min"], "k": ds["k"],
                                       "pts": pts if zones.h_img2floor else None}, zones.zones)
                print(f"[{win.label}] 대기 {queue:3d}명  처리 {lam:5.1f}/분  예상 {wait}분  {state}  추론 {infer_ms:.0f}ms  트랙 {len(tracks)}")
            else:                                                 # 창 밖(또는 mock 출처) — 기록 없음, 관리자만 실사를 본다
                print(f"[기록 없음{'·' + win.label if win else ''}] (관리자 열람 중: 실측 L={queue} λ={lam:.1f} 추론 {infer_ms:.0f}ms 트랙 {len(tracks)})")
        time.sleep(max(0, period - (time.monotonic() - t0)))


if __name__ == "__main__":
    main()
