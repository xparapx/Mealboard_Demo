"""시연영상 추가 장면 내레이션 — 대본(narr_extra.json) → mp3. 공급자: edge(마이크로소프트 엣지 신경망 음성, 키 없음) | openai(.env OPENAI_API_KEY, 인앱 아나운서와 같은 화자)

    python narrate.py <out_dir> [edge|openai] [voice]
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
PROVIDER = sys.argv[2] if len(sys.argv) > 2 else "edge"
VOICE = sys.argv[3] if len(sys.argv) > 3 else ("ko-KR-SunHiNeural" if PROVIDER == "edge" else "marin")

SCRIPT = {   # id: (목표 길이 초, 대본)
    "three":  (7.0,  "핵심은 셋입니다. 예상 대기시간, 급식실 밀집도, 그리고 영양과 운영 리포트."),
    "term":   (14.0, "파이도 카메라도 없이 노트북 한 대면 됩니다. 공공 깃랩에서 받은 폴더에서 이 한 줄, uv sync 와 jobs.demo 를 실행하면 모의 데이터가 만들어지고 서버가 뜹니다."),
    "app":    (17.0, "브라우저가 열리면 여섯 화면이 모의 데이터로 채워져 있습니다. 가상 시계는 10월 14일 점심 피크에서 시작하고, 화면 위 띠가 시연 모드임을 밝힙니다. 통계와 오늘 급식도 같은 코드로 계산된 값입니다."),
    "admin":  (10.0, "관리 화면의 AI 모델 선택 카드에서 엔진과 모델을 바꾸고, 점검을 돌리고, 되돌릴 수 있습니다."),
    "llm":    (9.0,  "하일로 칩, 올라마, 규칙 템플릿까지 같은 검증기로 실측했습니다. 운영 모델은 젬마 포 입니다."),
    "live":   (24.0, "지금 보시는 것은 실제 운영 화면입니다. 9월 11일부터 공주고 급식실에서 돌고 있고, 급식 시간이 아니면 안내만 보입니다. 히트맵과 통계는 지난 몇 주의 실측 집계이고, 평소 밀집도는 사람이 늘 모이는 자리를 숫자로 보여 줍니다."),
    "kiosk":  (17.0, "통행로의 42인치 모니터에는 10초마다 일곱 장이 돌아갑니다. 휴대폰이 없는 학생도 지나가며, 지금 줄을 서면 얼마나 기다리는지 봅니다."),
    "ending": (8.0,  "생활 공간의 작은 불편을 끝까지 숫자로 따라가면, 공공의 가치가 됩니다. 감사합니다."),
}
(OUT / "narr_extra.json").write_text(json.dumps({k: {"sec": v[0], "text": v[1]} for k, v in SCRIPT.items()}, ensure_ascii=False, indent=1), encoding="utf-8")


async def edge_all():
    import edge_tts
    for k, (sec, text) in SCRIPT.items():
        await edge_tts.Communicate(text, VOICE, rate="+8%").save(str(OUT / f"x_{k}.mp3"))
        print("edge", k)


def openai_all():
    import urllib.request
    from dotenv import load_dotenv
    load_dotenv(Path("C:/Users/phlox/PRJ/Mealboard_Demo/.env"))
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key: raise SystemExit("OPENAI_API_KEY 없음")
    narr = json.load(open("C:/Users/phlox/PRJ/Mealboard_Demo/static/media/voice/narration.json", encoding="utf-8"))["voice"]
    for k, (sec, text) in SCRIPT.items():
        body = {"model": narr.get("model", "gpt-4o-mini-tts"), "voice": VOICE, "input": text, "response_format": "mp3", "instructions": narr.get("instructions", "")}
        req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r: (OUT / f"x_{k}.mp3").write_bytes(r.read())
        print("openai", k)


if PROVIDER == "edge": asyncio.run(edge_all())
else: openai_all()

import mutagen
for k, (sec, text) in SCRIPT.items():
    d = mutagen.File(OUT / f"x_{k}.mp3").info.length
    print(f"{k:7s} {d:5.1f}s / 목표 {sec:4.1f}s {'!!' if d > sec - 0.6 else 'ok'}  ({len(text)}자)")
