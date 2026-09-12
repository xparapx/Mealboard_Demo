# Mealboard — 학교 급식실 대기시간·영양 대시보드

급식실 카메라(라즈베리파이 5 + YOLO)로 대기 인원·처리율을 재어 **예상 대기시간**(Little's law, W = L / λ)을 내고,
NEIS 급식 API 의 메뉴·알레르기·영양 지표(에너지 충족률·적정비율·MAR)와 주간 식단, 잔반 탄소 카드, 익명 위치 마커를 웹 대시보드(PWA)로 보여준다.
학생·교사는 QR 로 접속한다. 영상은 어디에도 저장·전송하지 않고 숫자만 SQLite 에 남긴다.

- 구축 매뉴얼(전 단계·코드 수록): [docs/manual.html](docs/manual.html) · 화면 도면(스펙의 단일 출처): [docs/layout.html](docs/layout.html)
- Claude Code 작업 규칙: [CLAUDE.md](CLAUDE.md)

## 구조

```
app/        FastAPI 공개 앱 — main.py, config.py(.env 단일 출처), db.py, lunch.py(급식 창), insight_calc.py(판정 규칙), insights_db.py(읽기 전용),
            mealjson.py, routers/{status,history,meal,positions,news,typical,insight}.py
app/admin/  관리 앱(별도 프로세스 8101, tailnet 전용) — server.py, auth.py, guard.py, sysctl.py, watchdog.py, audit.py, health.py,
            stream.py(메타 SSE 허브·MJPEG 프록시), zones_store.py(zones.local.json writer), routers/{system,stream,zones}.py, static/{admin.js,zones-editor.js,admin.css}
vision/     waittime.py(Little's law), zones.py(구역·ROI·호모그래피, 순수), meta.py(메타데이터 발신). counter·debug_stream 은 로드맵 ④
jobs/       mock_feed.py(카메라 대역, --meta), fetch_neis.py(→ meal.json), fetch_news.py + newsbody.py + translators.py(→ news.json),
            rollup.py(→ insights.db), report.py + report_templates.py + llm.py(→ reports.db)
static/     index.html(셸) · css/{base,screens,insight}.css · js/{core,floor,wait,room,week,today,news}.js(ES 모듈, 빌드 없음) · manifest.json · sw.js
data/       queue.db·insights.db·reports.db·admin.db·meal.json·news.json·positions.json·zones.local.json (git 제외)
            / nutrition_std.json·carbon_std.json·news_feeds.json·zones.json(템플릿) (포함)
deploy/     mealboard-{api,mock,vision,admin,neis,news,rollup,report}.service, *.timer, sudoers-mealboard, cloudflared-config.yml(견본)
tests/      순수 로직 140개 — waittime·typical·lunch·zones·insight_calc·mealjson·admin_{auth,guard,sysctl,stream,zones}·report·news
docs/       manual.html(구축 매뉴얼) · layout.html(화면 도면) · PLAN-2026-09.md(확장 계획서, §6 진행표)
setup_pi.sh Pi 최초 설치·유닛 갱신 (멱등) · check_manual.py 매뉴얼 코드 블록 ↔ 파일 대조
```

## 셋업 요약

- **개발 PC**: `uv venv && uv sync` → 창 1 `uv run python -m jobs.mock_feed --speed 60`, 창 2 `uv run uvicorn app.main:app --port 8100` → `http://localhost:8100/`. 테스트 `uv run pytest -q`.
- **Pi**: `bash setup_pi.sh` (클론·venv·systemd 유닛). 이후 배포는 `/opt/mealboard` 에서 `git pull` → 해당 서비스 `systemctl restart`.
- **외부 공개**: **Cloudflare Tunnel** — 공개 주소 **`https://kjhs-meal.com`**(도메인 `kjhs-meal.com` 은 Cloudflare Registrar 구매, 09-04). `deploy/mealboard-cloudflared.service` + `.env CF_TUNNEL_TOKEN`, 호스트 매핑은 Cloudflare 대시보드(`meal` → `127.0.0.1:8100`, 8101 금지). Tailscale Funnel(`https://rsp.taild5f11e.ts.net`)은 학교 망이 릴레이를 막아 휴대폰에서 끊기므로 예비. 자세한 절차는 매뉴얼 STEP 9.

## 작업 로그

작업 이력·세션 인계는 [docs/WORKLOG.md](docs/WORKLOG.md) 에 있다 (최신이 위). README 는 프로젝트 소개 전용 (09-12 개정).
