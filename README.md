# Mealboard — 학교 급식실 대기시간·영양 대시보드

급식실 카메라(라즈베리파이 5 + YOLO)로 대기 인원·처리율을 재어 **예상 대기시간**(Little's law, W = L / λ)을 내고,
NEIS 급식 API 의 메뉴·영양 지표(에너지 충족률·적정비율·MAR)와 잔반 탄소 카드, 익명 위치 마커를 웹 대시보드(PWA)로 보여준다.
학생·교사는 QR 로 접속한다. 영상은 어디에도 저장·전송하지 않고 숫자만 SQLite 에 남긴다.

- 구축 매뉴얼(전 단계·코드 수록): [docs/manual.html](docs/manual.html) · 화면 도면(스펙의 단일 출처): [docs/layout.html](docs/layout.html)
- Claude Code 작업 규칙: [CLAUDE.md](CLAUDE.md)

## 구조

```
app/        FastAPI — main.py, config.py, db.py, routers/{status,history,meal,positions}.py
vision/     waittime.py (순수 로직). counter·zones 등은 로드맵 ④
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
- 08-28 대시보드 전 구간 완료 — 영양 지표 3종·영양소 막대, 잔반 탄소 카드, 익명 위치 마커(평면도), 팔레트 v4·고도/모션 체계·데스크톱 2컬럼 — 와 Tailscale Funnel 공개(고정 주소) 완료. 남은 것: vision(카메라 카운팅)과 학교 Pi 이전·실측.
- 08-28 매뉴얼 STEP 11~13(탄소·이슈 링크·위치 마커) 추가, `check_manual.py` 로 코드 블록 ↔ 파일 동기화 자동화.
- 08-27 저장소 뼈대, systemd 유닛·setup_pi.sh, Little's law 함수+테스트, SQLite 스키마·API 3종, mock_feed, NEIS 급식·영양 지표.
