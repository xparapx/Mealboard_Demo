# 시연영상 자동 제작 (공모전 N7, 2026-11-08)

인앱 자동 시연(아나운서 mp3)과 실제 화면을 Playwright 로 녹화해 ffmpeg 로 한 편(≈4분 54초, 1920×1080 30fps, slideleft 전환)으로 조립한다. 도구는 전부 `uv run --with …` 로 임시 설치 — 저장소 의존성에 넣지 않는다.

```powershell
# 0. 로컬 데모(공개 8812 · 관리 8813) 를 띄워 둔다 — 관리 앱 주소(key 포함)는 터미널에 찍힌다
uv run python -X utf8 -u -m jobs.demo --no-browser --port 8812 --with-admin --data $env:TEMP\mb_demo_video
# 1. 카드 PNG(제목·핵심 셋·LLM 실측표·마무리)
uv run --with pillow python tools/demo_video/cards.py <작업폴더>/cards
# 2. 녹화(설치된 Edge, 소리는 음소거 — 음성은 후반에 mp3 로 입힌다). ADMIN_URL 에 관리 앱 주소
$env:ADMIN_URL="http://127.0.0.1:8813/?key=…"; $env:MUTE="1"
uv run --with playwright python -X utf8 tools/demo_video/rec.py <작업폴더>/out tour app admin live kiosk term
# 3. 조립 → mp4
uv run --with imageio-ffmpeg python -X utf8 tools/demo_video/post.py <작업폴더> <출력.mp4>
```

- `rec.py`: 시연은 `#wait` 에서 자홍색 동기 마커(0.5초)를 띄운 뒤 `MB.tour.start()` — 단계 전환(`MB.tour.step()`·인트로 점)과 mp3 `play()` 시각을 `performance.now()` 로 `tour.json` 에 기록. 다른 장면은 자막 띠를 DOM 에 주입해 함께 녹화.
- `post.py`: 마커 프레임으로 영상↔페이지 시간축을 맞추고(`KEEP` 단계만 잘라 5분 예산), 각 구간에 그 단계의 mp3(`playback_rate` 배속)를 단계 시작 뒤 실제 재생 시각에 맞춰 깐다. 장면·카드 길이는 `SCENE_LEN`·`CARD_LEN`. 모든 세그먼트를 같은 규격 mp4 로 만든 뒤 `xfade=slideleft` + `acrossfade` 로 잇는다.
- 함정: Playwright 첫 실행은 `python -m playwright install ffmpeg` 가 필요(Edge 는 `channel="msedge"` 로 설치본 사용) · ffmpeg 9 는 `-vsync` 대신 `-fps_mode` · `play()` 훅의 `currentSrc` 는 직전 파일을 가리키므로 이름이 아니라 시각으로 짝짓는다 · Windows drawtext 의 fontfile 경로 이스케이프가 까다로워 자막은 PNG/DOM 으로.
- 구성(순서): 제목 → 인트로 0·1·2 → 핵심 셋 카드 → s0 대기시간 → s2 예보 → s3 히트맵 → s6 익명 마커 → s7 밀집도 → s9 리포트 → s13 영양 → 터미널 한 줄 구동 → 앱 둘러보기 → 관리 'AI 모델 선택' → LLM 실측표 → 실운영 화면(kjhs-meal.com) → 키오스크 → 엔드카드(outro) → 마무리.
