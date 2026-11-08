"""시연영상 조립 — 녹화 webm + 시연 타임라인(tour.json) + 아나운서 mp3 + 카드 PNG → 1920×1080 30fps mp4, 장면 사이 slideleft 전환

    python post.py <rec_dir> <out_mp4>
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
REC = Path(sys.argv[1]); OUTV = Path(sys.argv[2])
O, SEG, CARDS, VOICE = REC / "out", REC / "seg", REC / "cards", Path("static/media/voice")
SEG.mkdir(exist_ok=True)
RATE = json.load(open(VOICE / "narration.json", encoding="utf-8")).get("playback_rate", 1.2)
XF = 0.5                                         # 전환 길이(초)
KEEP = ["intro0", "intro1", "intro2", "s0", "s2", "s3", "s6", "s7", "s9", "s13"]        # 시연 중 영상에 넣는 단계(5분 예산)
SCENE_LEN = {"term": 13.0, "app": 14.0, "admin": 14.0, "live": 20.0, "kiosk": 14.0}
CARD_LEN = {"title": 4.5, "three": 6.0, "llm": 9.0, "ending": 7.0, "stamp": 2.0}
# 장면 뒤 전환(없으면 컷). 인앱 구간은 인앱의 플립·카드 팬이 곧 전환이라 컷으로 두고, 챕터 경계만 서로 다른 전환 + 2초 스탬프
TRANS = {"title": ("fade", 1.0), "intro2": ("smoothleft", 0.7), "three": ("zoomin", 0.8), "s13": ("circleclose", 0.7),
         "stamp2": ("circleopen", 0.7), "term": ("slideleft", 0.6), "app": ("fadeblack", 0.6), "stamp3": ("radial", 0.8),
         "admin": ("smoothup", 0.6), "llm": ("fadeblack", 0.6), "stamp4": ("zoomin", 0.8), "live": ("slideleft", 0.6),
         "kiosk": ("fadeblack", 0.8), "outro": ("dissolve", 0.8)}


def run(args, quiet=True):
    r = subprocess.run([FF, "-hide_banner", "-y", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stderr[-3000:]); raise SystemExit("ffmpeg 실패: " + " ".join(args[:6]))
    return r.stderr


def duration(path):
    r = subprocess.run([FF, "-hide_banner", "-i", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def marker_offset(webm, t_perf_ms):
    """자홍색 전면 마커가 처음 보이는 영상 시각 - 페이지 performance.now() → 두 시간축의 차(초)"""
    raw = subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-t", "10", "-i", str(webm), "-vf", "fps=25,scale=8:8", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    n = len(raw) // 192
    for k in range(n):
        f = raw[k * 192:(k + 1) * 192]
        r, g, b = (sum(f[i::3]) / 64 for i in range(3))
        if r > 180 and g < 90 and b > 180:
            t_video = k / 25
            print(f"마커: 영상 {t_video:.2f}s ↔ 페이지 {t_perf_ms/1000:.2f}s")
            return t_video - t_perf_ms / 1000
    raise SystemExit("마커 프레임을 찾지 못했다")


ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", "30", "-fps_mode", "cfr",
       "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart"]
VF = "scale=1920:1080:flags=lanczos,setsar=1,format=yuv420p"


NARR = REC / "narr"                                # 추가 장면 내레이션 x_<id>.mp3(narrate.py, OpenAI TTS marin) — 있으면 깐다
def extra(name):
    p = NARR / f"x_{name}.mp3"
    return p if p.exists() else None


def seg_video(src, start, dur, out, audio=None, adelay=0.0, tempo=None):
    """webm 구간 → mp4. audio 가 있으면 그 mp3(배속 tempo, 기본 인앱 RATE)를 adelay 뒤에 깔고, 없으면 무음"""
    tempo = RATE if tempo is None else tempo
    if audio:
        af = f"[1:a]atempo={tempo},adelay={int(adelay*1000)}|{int(adelay*1000)},apad,atrim=0:{dur:.3f},asetpts=PTS-STARTPTS[a]"
        run(["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src), "-i", str(audio), "-filter_complex", f"[0:v]{VF}[v];{af}",
             "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}", *ENC, str(out)])
    else:
        run(["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src), "-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
             "-filter_complex", f"[0:v]{VF}[v]", "-map", "[v]", "-map", "1:a", "-t", f"{dur:.3f}", *ENC, str(out)])


def card_video(png, dur, out, audio=None, adelay=0.6):
    if audio:                                              # 추가 장면 내레이션도 인앱과 같은 배속(RATE)으로
        dur = max(dur, duration(audio) / RATE + adelay + 0.8)
        af = f"[1:a]atempo={RATE},adelay={int(adelay*1000)}|{int(adelay*1000)},apad,atrim=0:{dur:.3f},asetpts=PTS-STARTPTS[a]"
        run(["-loop", "1", "-framerate", "30", "-t", f"{dur:.3f}", "-i", str(png), "-i", str(audio), "-filter_complex", f"[0:v]{VF}[v];{af}",
             "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}", *ENC, str(out)])
        return
    run(["-loop", "1", "-framerate", "30", "-t", f"{dur:.3f}", "-i", str(png), "-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
         "-filter_complex", f"[0:v]{VF}[v]", "-map", "[v]", "-map", "1:a", "-t", f"{dur:.3f}", *ENC, str(out)])


# ---------- 1. 시연 타임라인 → 단계별 구간
tj = json.load(open(REC / "out" / "tour.json", encoding="utf-8"))
off = marker_offset(O / "tour.webm", tj["marker_perf"])
vt = lambda ms: ms / 1000 + off
steps = tj["steps"]
# play() 훅이 읽은 currentSrc 는 직전 파일을 가리킨다(새 src 적재 전) → 이름 대신 '단계 시작 뒤 첫 play 시각' 으로 짝을 짓는다
clips = {}
for k, s in enumerate(steps):
    t_end = steps[k + 1]["t"] if k + 1 < len(steps) else float("inf")
    cand = [c["t"] for c in tj["clips"] if s["t"] - 50 <= c["t"] < t_end]
    if cand: clips[s["id"]] = min(cand)
tour_len = duration(O / "tour.webm")
spans = {}
for k, s in enumerate(steps):
    t0 = vt(s["t"])
    if k + 1 < len(steps): t1 = vt(steps[k + 1]["t"])
    else: t1 = min(tour_len - 0.2, t0 + duration(VOICE / "outro.mp3") / RATE + 1.6)
    spans[s["id"]] = (t0, t1)
print("단계 구간:", {k: (round(a, 1), round(b - a, 1)) for k, (a, b) in spans.items()})

order = []                                        # (이름, mp4 경로)
def add(name, path): order.append((name, path))

card_video(CARDS / "title.png", CARD_LEN["title"], SEG / "c_title.mp4"); add("title", SEG / "c_title.mp4")
for sid in KEEP:
    if sid not in spans: print("없음:", sid); continue
    if sid == "s0":
        card_video(CARDS / "three.png", CARD_LEN["three"], SEG / "c_three.mp4", extra("three")); add("three", SEG / "c_three.mp4")
    a, b = spans[sid]; dur = b - a
    delay = max(0.0, vt(clips[sid]) - a) if sid in clips else 0.0
    out = SEG / f"t_{sid}.mp4"
    seg_video(O / "tour.webm", a, dur, out, VOICE / f"{sid}.mp3" if sid in clips else None, delay)
    add(sid, out); print(f"  {sid}: {dur:.1f}s (음성 +{delay:.2f}s)")

for sc in ("term", "app", "admin", "live", "kiosk"):
    if sc == "term": card_video(CARDS / "stamp2.png", CARD_LEN["stamp"], SEG / "c_stamp2.mp4"); add("stamp2", SEG / "c_stamp2.mp4")
    if sc == "admin": card_video(CARDS / "stamp3.png", CARD_LEN["stamp"], SEG / "c_stamp3.mp4"); add("stamp3", SEG / "c_stamp3.mp4")
    if sc == "live": card_video(CARDS / "stamp4.png", CARD_LEN["stamp"], SEG / "c_stamp4.mp4"); add("stamp4", SEG / "c_stamp4.mp4")
    src = O / f"{sc}.webm"
    if not src.exists(): print("녹화 없음:", sc); continue
    start = {"term": 0.6, "kiosk": 5.2}.get(sc, 0.3)        # 키오스크는 첫 슬라이드가 약 5초 뒤에 뜬다(공개 데모 응답 대기)
    if sc == "admin" and (O / "admin.json").exists():       # 관리 장면은 녹화 스크립트가 적은 '관리 화면이 뜬 시각' 부터
        start = json.load(open(O / "admin.json"))["start"]
    avail = duration(src) - start - 0.2
    x = extra(sc); want = SCENE_LEN[sc]
    xl = duration(x) / RATE if x else 0.0                  # 인앱과 같은 배속으로 재생한 길이
    if x: want = max(want, xl + 1.4)                       # 내레이션이 길면 장면을 그만큼(녹화 범위 안에서) 늘린다
    d = min(want, avail)
    if x and xl + 0.6 > d: print(f"  주의: {sc} 내레이션 {xl:.1f}s > 장면 {d:.1f}s")
    seg_video(src, start, d, SEG / f"s_{sc}.mp4", x, 0.5 if x else 0.0); add(sc, SEG / f"s_{sc}.mp4")
    if sc == "admin":
        card_video(CARDS / "llm.png", CARD_LEN["llm"], SEG / "c_llm.mp4", extra("llm")); add("llm", SEG / "c_llm.mp4")
if "outro" in spans:
    a, b = spans["outro"]; delay = max(0.0, vt(clips["outro"]) - a)
    seg_video(O / "tour.webm", a, b - a, SEG / "t_outro.mp4", VOICE / "outro.mp3", delay); add("outro", SEG / "t_outro.mp4")
card_video(CARDS / "ending.png", CARD_LEN["ending"], SEG / "c_ending.mp4", extra("ending")); add("ending", SEG / "c_ending.mp4")

# ---------- 2-A. 컷으로 이어지는 장면은 먼저 하나로 붙인다(concat) → 그룹 사이만 전환
groups, cur, trans = [], [], []
for name, path in order:
    cur.append((name, path))
    if name in TRANS:
        groups.append(cur); trans.append(TRANS[name]); cur = []
if cur: groups.append(cur)
gpaths = []
for gi, g in enumerate(groups):
    if len(g) == 1: gpaths.append(g[0][1]); continue
    lst = SEG / f"g{gi}.txt"
    lst.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for _, p in g), encoding="utf-8")
    out = SEG / f"g{gi}.mp4"
    run(["-f", "concat", "-safe", "0", "-i", str(lst), *ENC, str(out)])
    gpaths.append(out); print(f"  그룹 {gi}: {' + '.join(n for n, _ in g)} → {duration(out):.1f}s")

# ---------- 2-B. 그룹 사이 xfade(종류·길이는 TRANS) + acrossfade
durs = [duration(p) for p in gpaths]
total = sum(durs) - sum(d for _, d in trans)
print("장면", len(order), "그룹", len(gpaths), "합계", round(sum(durs), 1), "s → 전환 뒤", round(total, 1), "s =", f"{int(total//60)}:{total%60:04.1f}")
inputs = []; [inputs.extend(["-i", str(p)]) for p in gpaths]
fc = []; vprev, aprev = "[0:v]", "[0:a]"; offset = 0.0
for k in range(1, len(gpaths)):
    kind, xf = trans[k - 1]
    offset += durs[k - 1] - xf
    vo, ao = f"[v{k}]", f"[a{k}]"
    fc.append(f"{vprev}[{k}:v]xfade=transition={kind}:duration={xf}:offset={offset:.3f}{vo}")
    fc.append(f"{aprev}[{k}:a]acrossfade=d={xf}:c1=tri:c2=tri{ao}")
    vprev, aprev = vo, ao
run([*inputs, "-filter_complex", ";".join(fc), "-map", vprev, "-map", aprev, *ENC, "-t", f"{total:.3f}", str(OUTV)], quiet=False)
print("완료:", OUTV, f"{OUTV.stat().st_size/1e6:.1f} MB", f"{duration(OUTV):.1f}s")
