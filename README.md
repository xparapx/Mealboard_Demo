# Mealboard — 학교 급식실 대기시간·영양 대시보드

급식실 카메라(라즈베리파이 5 + YOLO)로 대기 인원·처리율을 재어 **예상 대기시간**(Little's law, W = L / λ)을 내고,
NEIS 급식 API 의 메뉴·알레르기·영양 지표(에너지 충족률·적정비율·MAR)와 주간 식단, 잔반 탄소 카드, 익명 위치 마커를 웹 대시보드(PWA)로 보여준다.
학생·교사는 QR 로 접속한다. 영상은 어디에도 저장·전송하지 않고 숫자만 SQLite 에 남긴다.

- 구축 매뉴얼(전 단계·코드 수록): [docs/manual.html](docs/manual.html) · 화면 도면(스펙의 단일 출처): [docs/layout.html](docs/layout.html)
- Claude Code 작업 규칙: [CLAUDE.md](CLAUDE.md)

## 구조

```
app/        FastAPI — main.py, config.py, db.py, routers/{status,history,meal,positions,news,typical}.py
vision/     waittime.py (순수 로직). counter·zones 등은 로드맵 ④
tests/      test_waittime.py (Little's law), test_typical.py (평소 곡선의 시간창)
jobs/       mock_feed.py (카메라 대역, positions.json 도 씀), fetch_neis.py (하루 1회 → data/meal.json)
static/     index.html (대시보드 단일 파일), manifest.json, sw.js
data/       queue.db·meal.json·positions.json (git 제외) / nutrition_std.json·carbon_std.json (기준·계수, 포함)
deploy/     mealboard-{api,mock,neis}.service, mealboard-neis.timer, cloudflared-config.yml(견본)
docs/       manual.html, layout.html
setup_pi.sh Pi 최초 설치·유닛 갱신 (멱등) · check_manual.py 매뉴얼 코드 블록 ↔ 파일 대조
```

## 셋업 요약

- **개발 PC**: `uv venv && uv sync` → 창 1 `uv run python -m jobs.mock_feed --speed 60`, 창 2 `uv run uvicorn app.main:app --port 8100` → `http://localhost:8100/`. 테스트 `uv run pytest -q`.
- **Pi**: `bash setup_pi.sh` (클론·venv·systemd 유닛). 이후 배포는 `/opt/mealboard` 에서 `git pull` → 해당 서비스 `systemctl restart`.
- **외부 공개**: 스테이징·시범 운영은 Tailscale Funnel(`tailscale funnel --bg 8100`, 고정 주소). 정식 배포 시 Cloudflare Tunnel + 유료 도메인. 자세한 절차는 매뉴얼 STEP 9.

## 작업 로그

### 2026-08
- 08-29 화면 확정 — 위치 마커 스마일, 이번 주 식단을 요일 컬럼 + 요일 5색으로, 긴 메뉴명 줄바꿈, 데스크톱 두 패널 아래 끝 맞춤(짧은 쪽 마지막 카드가 흡수하고 평면도는 그만큼 커진다). 이슈 링크는 해외 기후 매체 4곳(Carbon Brief·Inside Climate News·The Guardian·Yale Climate Connections) + 피드 요약 + DeepL 한국어 번역. `docs/layout.html` 도면 v5 동반 갱신.
- 08-29 `static/sw.js` 서비스워커 재작성 — 화면은 네트워크 우선, `activate` 에서 옛 캐시 삭제 + `clients.claim()`, `skipWaiting()`. v1 은 캐시 이름이 고정이고 화면까지 캐시 우선이라 **배포해도 브라우저에 도달하지 않았다**(v5 배포에서 실제로 겪음).
- 08-29 주말·공휴일(`today` 가 null)에도 이번 주 식단 카드를 보여주도록 수정. 오늘 강조는 캐시된 `today.date` 가 아니라 브라우저 시계 기준.
- 08-29 **대시보드 v5** — 전 카드의 1.5px 외곽선을 걷어내고 라운드 24 + 2단 그림자로 재설계(팔레트 3색은 유지). 네 가지 추가: ① 알레르기 표시(NEIS 가 메뉴명에 붙여 보내던 번호를 분리, 내 항목은 브라우저에만 저장) ② 이번 주 식단(`meal.json` 의 `week[]` — 서버 변경 없음) ③ 배식대 도착 시각 ④ 평소 곡선(`/api/typical` 신설, 같은 요일 우선·표본 부족 시 최근 7일 폴백). 뺀 것: 잔반 자기신고 4버튼과 개인 월간 누적, 영양소 막대 6색(색 검증 전 항목 탈락 → 상태 2색 칩으로 대체). 도면 v5(`docs/layout.html`)·매뉴얼 STEP 14 동반 갱신.
- 08-29 개발 PC → Pi SSH 키 로그인 구성(`mbpi` 별칭), `.env.example` 에 `PI_USER`·`PI_HOST` 추가.
- 08-28 대시보드 전 구간 완료 — 영양 지표 3종·영양소 막대, 잔반 탄소 카드, 익명 위치 마커(평면도), 팔레트 v4·고도/모션 체계·데스크톱 2컬럼 — 와 Tailscale Funnel 공개(고정 주소) 완료. 남은 것: vision(카메라 카운팅)과 학교 Pi 이전·실측.
- 08-28 매뉴얼 STEP 11~13(탄소·이슈 링크·위치 마커) 추가, `check_manual.py` 로 코드 블록 ↔ 파일 동기화 자동화.
- 08-27 저장소 뼈대, systemd 유닛·setup_pi.sh, Little's law 함수+테스트, SQLite 스키마·API 3종, mock_feed, NEIS 급식·영양 지표.
