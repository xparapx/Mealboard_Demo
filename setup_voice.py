"""자동 시연 아나운서 음성 녹음(10-19) — static/media/voice/narration.json 의 대본을 OpenAI TTS 로 읽어 같은 폴더에 <id>.mp3 를 만든다.

    uv run python setup_voice.py            # 없는 클립만 만든다
    uv run python setup_voice.py --force    # 전부 다시
    uv run python setup_voice.py --only s0 intro1
    uv run python setup_voice.py --dry-run  # 글자 수·예상 비용만

키는 로컬 .env 의 OPENAI_API_KEY (setup_tts_key.ps1 로 넣는다). 채팅·커밋·로그에 키를 두지 않는다. 표준 라이브러리만 쓴다(SDK 없음).
만들어진 mp3 는 git 에 커밋한다(≈20클립, 수 MB) — 심사위원·공개 데모가 같은 음성을 듣게. guide.js 는 mp3 가 있으면 재생, 없으면 브라우저 음성으로 같은 대본을 읽는다.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")       # Windows 콘솔(cp949)에서도 한글·기호가 깨지지 않게

BASE = Path(__file__).resolve().parent
VOICE_DIR = BASE / "static" / "media" / "voice"
SCRIPT = VOICE_DIR / "narration.json"
URL = "https://api.openai.com/v1/audio/speech"
PRICE_PER_1M = 12.0        # gpt-4o-mini-tts 대략 $12 / 1M 입력 글자(2026 기준 안내 — 변동 가능)


def load():
    doc = json.loads(SCRIPT.read_text(encoding="utf-8"))
    return doc["voice"], doc["clips"]


def synth(key, cfg, text, out):
    body = {"model": cfg.get("model", "gpt-4o-mini-tts"), "voice": cfg.get("voice", "nova"), "input": text,
            "response_format": "mp3", "speed": cfg.get("speed", 1.0)}
    if cfg.get("instructions"):
        body["instructions"] = cfg["instructions"]
    req = urllib.request.Request(URL, data=json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            out.write_bytes(data)
            return len(data)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise SystemExit(f"{out.name}: HTTP {e.code} — {msg}")
    raise SystemExit(f"{out.name}: 재시도 실패")


def write_doc(out=BASE / "docs" / "NARRATION.md"):
    """매핑표 docs/NARRATION.md 재생성(10-19) — narration.json(대본·음성 설정) + static/js/guide.js(INTRO·STEPS·OUTRO) 를 합친 파생 문서"""
    import re
    narr = json.loads(SCRIPT.read_text(encoding="utf-8"))
    src = (BASE / "static" / "js" / "guide.js").read_text(encoding="utf-8")

    def parse(name):
        i = src.index(f"const {name} = [")
        j = src.index("\n];", i)
        pat = r'\{\s*(?:screen:\s*"(?P<screen>[^"]*)",\s*sel:\s*"(?P<sel>[^"]*)",\s*)?title:\s*"(?P<title>[^"]*)",\s*text:\s*"(?P<text>[^"]*)"'
        return [m.groupdict() for m in re.finditer(pat, src[i:j])]

    steps, intro = parse("STEPS"), parse("INTRO")
    om = re.search(r'const OUTRO = \{ title: "([^"]*)", text: "([^"]*)"', src)
    clips = {c["id"]: c["text"] for c in narr["clips"]}
    screen_ko = {"wait": "대기시간", "room": "실시간뷰", "stats": "통계", "week": "주간식단", "today": "오늘급식", "guide": "앱 안내"}
    v, rate = narr["voice"], narr.get("playback_rate", 1.0)
    sizes = {q.stem: q.stat().st_size for q in VOICE_DIR.glob("*.mp3")}

    def est(t):
        return round(len(t) / 4.6 / rate)                 # 한국어 TTS ≈4.6자/초(1.0배) ÷ 재생 배속 — 추정치

    rows, total = [], 0

    def add(n, cid, where, title):
        nonlocal total
        t = clips.get(cid, "")
        sec = est(t)
        total += sec
        rows.append(f"| {n} | `{cid}` | {where} | {title} | {t} | {len(t)}자 · 약 {sec}초 · {sizes.get(cid, 0) // 1024} KB |")

    for k, it in enumerate(intro):
        add(f"인트로 {k + 1}", f"intro{k}", "전면 카드(차콜)", it["title"])
    for k, st in enumerate(steps):
        add(f"{k + 1}", f"s{k}", f"{screen_ko.get(st['screen'], st['screen'])} · `{st['sel']}`", st["title"])
    add("엔드", "outro", "전면 카드", om.group(1))
    missing = [c for c in clips if c not in sizes]
    nl = "\n"
    lines = [
        "# 자동 시연 아나운서 대본 — 음성 매핑표", "",
        "> 자동 생성 문서(`uv run python setup_voice.py --doc`). **원본은 두 파일**이다 — 대본·음성 설정은 `static/media/voice/narration.json`, 단계(화면·카드·말풍선)는 `static/js/guide.js` 의 `INTRO`·`STEPS`·`OUTRO`.",
        "> 클립 id 는 두 파일에서 1:1(intro0~3 · s0~s14 · outro)이다. 단계를 더하거나 빼면 대본도 같이 고친다(`tests/test_voice_script.py` 가 개수·id 를 검사).", "",
        "## 음성 설정", "",
        "| 항목 | 값 |", "|---|---|",
        f"| 공급자 · 모델 | {v['provider']} · {v['model']} |",
        f"| 화자(페르소나) | **{v['voice']}** |",
        f"| 톤 지시(instructions) | {v['instructions']} |",
        f"| 생성 속도 / 재생 배속 | {v.get('speed', 1.0)} / **{rate}** (`playback_rate` — guide.js 가 mp3 `playbackRate` 와 브라우저 음성 `rate` 에 공통 적용, 재생성 없이 조절) |",
        f"| 클립 수 · 총 재생 추정 | {len(clips)}클립 · 약 {total // 60}분 {total % 60}초(배속 적용, 단계 사이 0.9초 간격 제외, 추정) |",
        "| 파일 | `static/media/voice/<id>.mp3` (git 추적, 심사위원·공개 데모 동일 음성) |", "",
        "## 매핑표", "",
        "화면의 말풍선 제목·본문(guide.js)은 **짧은 자막**이고, 아나운서 대본(narration.json)은 그 카드의 **맥락을 풀어 읽는 글**이다 — 둘은 의도적으로 다르다.",
        "분(分) 단위 숫자는 대본에서 한글로 적는다('10분' 은 TTS 가 사람 수 '열 분' 으로 읽었다).", "",
        "| 순서 | 클립 | 화면 · 카드 | 말풍선 제목 | 아나운서 대본 | 분량 |", "|---|---|---|---|---|---|",
        *rows, "",
        "## 고치는 방법", "",
        "1. 대본 문구: `narration.json` 의 해당 클립 `text` 수정 → `uv run python setup_voice.py --only <id>` (그 클립만 재생성, 클립당 ≈$0.002) → `--doc` 으로 이 표 갱신 → mp3·문서 커밋·push → Pi `git pull`(정적 파일이라 재시작 불필요).",
        "2. 화자·톤: `narration.json` 의 `voice`(nova·coral·shimmer·sage·marin 등)·`instructions` 수정 → `setup_voice.py --force`(20클립 ≈$0.03).",
        "3. 빠르기만: `playback_rate` 숫자만 바꾸고 커밋(재생성 없음). 생성 속도 `speed` 는 억양이 변하므로 1.0 유지 권장.",
        "4. 단계 추가·삭제: `guide.js` 의 `STEPS` 와 `narration.json` 의 clips 를 같이 고치고 `uv run python -m pytest tests/test_voice_script.py`.",
        "5. 키: 로컬 `.env OPENAI_API_KEY` 뿐(`setup_tts_key.ps1` 로 입력). 저장소·채팅·로그에 두지 않는다.",
    ]
    if missing:
        lines += ["", "**mp3 없는 클립**: " + ", ".join(missing)]
    out.write_text(nl.join(lines) + nl, encoding="utf-8", newline="\n")
    print(f"문서 → {out}  ({len(rows)}행, 총 재생 추정 {total}초)")



def main():
    ap = argparse.ArgumentParser(description="시연 아나운서 대본 → mp3 (OpenAI TTS)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--doc", action="store_true", help="docs/NARRATION.md 매핑표만 다시 만든다(생성 없음)")
    a = ap.parse_args()
    if a.doc:
        write_doc()
        return 0

    cfg, clips = load()
    if a.only:
        clips = [c for c in clips if c["id"] in set(a.only)]
    todo = [c for c in clips if a.force or not (VOICE_DIR / f"{c['id']}.mp3").exists()]
    chars = sum(len(c["text"]) for c in todo)
    print(f"대본 {len(clips)}클립, 만들 것 {len(todo)}클립, {chars:,}자 ≈ ${chars / 1e6 * PRICE_PER_1M:.3f}  (모델 {cfg.get('model')} · 음성 {cfg.get('voice')})")
    if a.dry_run or not todo:
        return 0

    load_dotenv(BASE / ".env")
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        print("OPENAI_API_KEY 가 .env 에 없다 — 저장소 루트에서  & .\\setup_tts_key.ps1  로 넣는다(키는 화면에 보이지 않는다)")
        return 1
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    for c in todo:
        out = VOICE_DIR / f"{c['id']}.mp3"
        n = synth(key, cfg, c["text"], out)
        print(f"  {c['id']:7s} {len(c['text']):4d}자 → {n / 1024:6.1f} KB")
    print(f"완료 → {VOICE_DIR}  (git add 해서 커밋한다)")
    write_doc()
    return 0


if __name__ == "__main__":
    sys.exit(main())
