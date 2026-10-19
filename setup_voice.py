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


def main():
    ap = argparse.ArgumentParser(description="시연 아나운서 대본 → mp3 (OpenAI TTS)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
