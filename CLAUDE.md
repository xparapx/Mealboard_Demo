# CLAUDE.md — Mealboard (학교 급식 모니터링 대시보드)

> 이 파일은 Claude Code 작업 지침이다. 저장소 루트에 두면 모든 세션이 자동으로 읽는다.
> 사람용 문서는 README.md와 docs/, 기계(Claude)용 규칙은 이 파일 — 역할을 섞지 말 것.

## 0. 현재 상태 (2026-08) — 세션 시작 시 먼저 읽을 것

- **홈 Pi 5(64bit, Debian 13 Trixie, 시스템 Python 3.13) = 스테이징.** 학교 Pi도 같은 OS·Python이어야 uv.lock이 그대로 맞는다. 카메라 없음 → `mealboard-vision` 미설치, `mealboard-mock`이 대역.
  로드맵 ④는 개발 PC 웹캠·동영상 파일로 진행. ⑤ 중 uv 셋업·systemd·외부 공개는 홈 Pi 완료, calibrate만 학교 Pi 이전 시.
- **외부 공개**: 스테이징·시범 운영은 **Tailscale Funnel**(고정 주소 `https://rsp.taild5f11e.ts.net`, `tailscale funnel --bg 8100`, 재부팅 유지).
  정식 배포 전환 시 Cloudflare Tunnel + 유료 도메인(cloudflared 는 Pi 에 설치 완료). kro.kr 류 무료 하위 도메인은 Cloudflare 에 등록 불가.
- **PI_HOST는 Tailscale 주소**(.env 참조). 공용 체크아웃은 `/opt/mealboard`. **Pi에서 직접 편집 금지, `git pull`만.**
  개발은 각자 PC의 클론에서 하고 Claude Code도 PC에서 실행해 SSH로 Pi를 제어한다.
- **같은 Pi에 Plant 프로젝트가 정지 상태로 공존**(`~/plant/`, planthub·plantdash·plantsnap 유닛).
  `~/plant/`와 그 DB에는 어떤 이유로도 접근·수정하지 않는다. 포트 8000·8501·1883은 Plant 소유.
- 홈 Pi에서는 vision 프레임 소스로 `picamera`를 쓰지 않는다(Plant 카메라 타이머와 배타 자원). `webcam|file`만.
- NEIS 인증키(개발계정) 발급 완료. 학교코드 8140036(공주고, 남고), 교육청 N10.
- **화면은 v5 확정**(2026-08-29 배포). 도면의 단일 출처는 `docs/layout.html`(v5), 구축 절차는 매뉴얼 STEP 14.
  카드에 외곽선을 두지 않는다 — 깊이는 radius 24 + 2단 그림자로. 바탕 `#F5F2E9` / 카드 `#FFFCF6`, 브랜드 3색은 유지.
  위치 마커는 노란 스마일(테두리 없음, 1.4초 점멸), 이번 주 식단은 요일이 컬럼(요일 5색, 오늘만 차콜), 데스크톱 두 패널은 아래 끝을 맞춘다.
- **`static/sw.js` 는 화면을 네트워크 우선으로 받는다.** 캐시 우선으로 되돌리지 말 것 — v1 이 그랬다가 배포가
  브라우저에 도달하지 못했다. 화면이 크게 바뀌면 `CACHE` 이름을 올린다(이름이 곧 무효화 스위치).
- **이슈 링크는 해외 기후 매체 4곳**(Carbon Brief · Inside Climate News · The Guardian · Yale Climate Connections)에서
  제목·피드 요약을 받아 **DeepL API Free** 로 한국어로 옮긴다. 키는 Pi `.env` 의 `DEEPL_API_KEY`(동작 확인 완료).
  키가 없거나 호출이 실패하면 원문 영어로 나갈 뿐 아무것도 깨지지 않는다. 요약은 반드시 문장 경계에서 자른다 —
  조각난 문장을 번역기에 주면 끊긴 한국어가 나온다.
- **개발 PC → Pi 는 키 로그인.** 어느 PC든 `ssh mbpi` 한 마디로 붙는다(`~/.ssh/config`, User `xparapx`, HostName `rsp`).
  키 파일은 PC 마다 다르다(맥북 `id_ed25519_mealboard`, jh-home PC `id_ed25519`) — Pi 의 `authorized_keys` 에 PC 별로 한 줄씩.
  새 PC 는 공개키를 Pi 콘솔에서 `authorized_keys` 에 추가한 뒤 위 별칭을 만든다. `.env` 의 `PI_USER`·`PI_HOST` 와 같은 값.
- **QR·PWA 아이콘은 할 일이 아니다(09-03 확인)**: Pi 의 `qr.png`·`static/icons/qr.png` 는 매뉴얼 STEP 9 의 `qrencode` 로
  만든 접속용 QR(내용 = Funnel 주소)이며 git 미추적이 맞다 — 한 줄로 재생성 가능. `static/icons/icon-192.png` 는 Pi 에도
  원래 없고(404) 매뉴얼대로 없어도 동작한다. 재설치 시 "깨지는" 것은 없다.
- **확장 계획서 `docs/PLAN-2026-09.md`(09-03 승인)가 다음 작업의 단일 출처.** 단계: 0 규칙 개정 → 1 집계 DB·`/api/insight/*` →
  2 프론트 5화면(모바일 하단 dock `#wait #room #week #today #news`, 데스크톱 보드+좌측 레일, 인사이트 카드는 주제별 화면 아래) →
  3 tailnet 전용 관리 앱(8101, Serve 8443, 허용목록) → 4 로컬 LLM(Hailo GenAI) 리포트·기사 본문 요약 → 5 문서. 단계마다 사용자 확인.
  파일당 쓰기 주체 하나(§2 DB 행), 개별 좌표·프레임 저장 금지는 그대로다.
- **다음 할 일**: PLAN §6 순서대로 — 지금은 **Phase 1a**(config·lunch·zones·zone_samples). 아래 ①~④ 는 그 안에 흡수된다.
  ① 평소 곡선(`/api/typical`)은 mock 이 170분 사이클을 반복해 써서 스테이징에서는 값이 바닥이다. 실측 이후 확인.
  ② Inside Climate News 는 미국 지역 전력·정치 보도가 많아 "세계적 기후 이슈"와 결이 다른 기사가 섞인다 —
  며칠 지켜본 뒤 교체 여부 판단(후보: UNEP · Climate Home News). ③ 급식 있는 평일에 데스크톱 2컬럼 높이 맞춤 실물 확인.
  ④ 로드맵 ④ vision 프로토타입.

## 1. 프로젝트 한 줄 정의

급식실 카메라(라즈베리파이 5 + YOLO)로 대기 인원·처리율을 측정해 **예상 대기시간**을 산출하고,
NEIS 급식 API의 메뉴·영양 정보와 함께 웹 대시보드(PWA)로 제공한다. 학생·교사가 QR로 접속한다.

## 2. 확정된 설계 결정 (재논의 금지, 변경 시 사용자 승인 필요)

| 항목 | 결정 | 근거 |
|---|---|---|
| 실행 위치 | 전부 Pi (셀프 호스팅, 모델 B) | 카메라가 Pi에 물리적으로 있음. Netlify 등 호스팅으로 대체 불가(서버가 Pi 안) |
| DB | SQLite (WAL 모드), **파일당 쓰기 주체 하나** | `queue.db`=vision(또는 mock) · `insights.db`=`jobs/rollup.py` · `reports.db`=`jobs/report.py` · `admin.db`·`data/zones.json`=관리 앱. **공개 app 은 SELECT 만** |
| 백엔드 | FastAPI 단일 Python 스택 | vision 프로세스와 언어 통일. **Pi에 Node.js 설치 금지** |
| API 포트 | **8100** (.env `API_PORT`), 127.0.0.1 바인딩. 관리 앱 **8101**(`ADMIN_PORT`), vision 디버그 MJPEG **8102**(`DEBUG_PORT`), 메타데이터 소켓 `/run/mealboard/meta.sock` — 전부 127.0.0.1 | 8000·8501·1883 은 Plant. **Funnel(공개)은 8100 만**, 관리 앱은 `tailscale serve --https=8443`(tailnet 전용)으로만 내보낸다. `serve reset`·`funnel reset` 금지(Funnel 443 까지 지워진다) |
| 프론트 | static/ 정적 파일 + fetch 폴링(30초) | React 필요 시 개발 PC에서 빌드한 dist만 복사 |
| 외부 노출 | 스테이징·시범 운영: **Tailscale Funnel**(고정 주소, 443 아웃바운드). 정식 배포: Cloudflare Tunnel + 유료 도메인 | 학교망 인바운드 차단 대응. 포트포워딩 금지. 둘 다 Pi 가 밖으로 연결을 여는 방식. 팀 SSH 는 tailnet 내부(Funnel 은 공개, 용도 구분) |
| 대기시간 | Little's law: W = L / λ | L=ROI 점유 인원, λ=배식대 가상선 통과율(5분 이동평균). **ROI 출구변 = λ 측정선**(같은 경계). λ < 0.5명/분이면 `insufficient_rate`로 산출 불가 처리 |
| 카운팅 | YOLOv8n/11n + ByteTrack, 기준점은 bbox 바닥 중앙 | 라인크로싱은 부호 변화 + ±20px 완충띠. `imgsz`·프레임 스킵은 설정으로 뺀다(Pi 5 CPU 수 fps) |
| 영상 취급 | **프레임 저장·전송 절대 금지. 숫자만 DB에** | 개인정보 원칙. 학교 협의의 전제 조건. 유일한 예외 = 승인된 디버그 경로(09-03): 관리 앱이 tailnet 안에서만 중계하는 MJPEG(뷰어 1명, ≤10분, 감사 기록, 디스크 접촉 없음) |
| 디버그 뷰 | 카운트 프로세스 내장, 127.0.0.1 전용 MJPEG, 터치파일(/tmp/debug_on)로 on/off(관리 앱이 켜고 끈다, ≤10분 자동 off, vision 도 mtime 10분 초과면 스스로 끈다. 두 유닛 모두 `PrivateTmp` 금지) | 관리자만 **SSH 터널 또는 tailnet 전용 관리 앱**(Serve 8443 + `ADMIN_USERS` 허용목록)으로 열람. 켜짐 이력(누가·언제·얼마나)은 `data/admin.db` |
| 히트맵 | 공개 화면은 빈 평면도 위 히트맵·익명 위치 마커(순간 상태만, 개별 위치 이력 저장 없음). 실사+마커는 디버그 뷰 전용. **공간 인사이트는 집계 숫자만**(구역별 점유율·통로 점유 등, 09-03 승인) — 개별 좌표·궤적은 어떤 형태로도 저장하지 않는다 | 마커는 `data/positions.json` 한 파일을 덮어쓰기만 하며 `/api/positions` 가 120초 stale 규칙으로 내준다. 집계는 `jobs/rollup.py` 가 `data/insights.db` 에 쓴다(구역 인원수는 vision/mock 이 `queue.db.zone_samples` 에 숫자만 기록). 관리 앱의 **메타데이터 스트림**(bbox·트랙 ID·바닥 좌표)은 인증된 관리자가 구독 중일 때만 실시간 중계 — 저장·버퍼 없음, 구독 이력은 admin.db |
| NEIS | `jobs/fetch_neis.py`가 하루 1회(systemd timer 05:40) `data/meal.json` 캐시 → 프론트는 `/api/meal`만 | 키 노출·호출 제한 방지. **프론트에서 NEIS 직접 호출 금지**. 주말·방학의 INFO-200은 오류가 아닌 `no_meal` |
| 영양 지표 | **에너지 충족률 · 에너지 적정비율(탄55~65/단7~20/지15~30%) · MAR** 세 가지. 코사인 유사도 사용 안 함 | 코사인은 단위 큰 성분(kcal·칼슘·비타민A)이 지배하고 크기 불변. 기준은 `data/nutrition_std.json`(학교별 1행), 영양소별 판정은 EAR~RNI 범위 |
| 해석 AI | 기본은 숫자→텍스트 LLM. **1순위 로컬 LLM(Hailo-10H GenAI, `jobs/llm.py`)**, 실패·미설치 시 규칙 템플릿. VLM은 예외 경로(디버그·calibrate 보조) | 카운팅 트랙과 SQLite로 완전 분리. 입력은 숫자·정제된 메뉴명·(기사 요약에 한해) 본문뿐 — 프레임·좌표는 절대 넣지 않는다. 출력은 스키마 검증(숫자 부분집합 규칙) 후에만 저장. **점심시간 밖에서만 실행**(HAT·CPU 경합 회피) |
| 뉴스 | `jobs/fetch_news.py` 가 하루 1회(06:10) 본문을 확보(RSS 전문 → Guardian API → HTML 단락 → 피드 요약)해 **로컬 LLM 한국어 요약(`digest`)** 을 만들고, 실패 시 DeepL 도입부 번역, 그마저 실패면 원문 영어 | 본문은 메모리에서만 쓰고 저장하지 않는다. 화면에는 짧은 자체 요약 + 출처 링크만(저작권). 헤드라인 번역기는 `TRANSLATOR`(deepl · local · none, 기본 deepl) |

## 3. 저장소 구조 (선행 레포 계승)

선행 레포 `Arduino_MQTT_MultiNode_Demo`, `Plant_Growth_Monitoring_Demo`의 규약을 따른다:
- 최상위는 **역할 폴더** + README.md + .gitignore
- `docs/` = GitHub Pages: `index.html`(프로젝트개요) + `manual.html`(구축 매뉴얼, 모든 코드 `<pre>` 수록 + 복사 버튼, 한국어, 처음 나오는 용어는 그 자리에서 설명)
- README 말미에 **「작업 로그」** 절 유지 (yyyy-mm 단위, 최신이 위)
- **systemd 유닛 파일은 저장소 `deploy/`에 포함** — Plant에서 Pi에 직접 만들어 새 Pi로 따라오지 못한 교훈. 설치는 `setup_pi.sh`가 한다

```
Mealboard_Demo/
├── CLAUDE.md                     # 이 파일
├── README.md                     # 개요·구조·셋업·작업 로그 (선행 레포 형식)
├── setup_pi.sh                   # Pi 최초 설치 + 유닛 갱신 (멱등)
├── docs/                         # GitHub Pages (index.html + manual.html)
├── app/                          # FastAPI: main.py, config.py, db.py, lunch.py, insight_calc.py, insights_db.py, routers/{status,history,meal,positions,news,typical,insight}.py, admin/(관리 앱, 별도 프로세스)
├── vision/                       # counter.py(진입점), source.py(webcam|file|picamera), zones.py, waittime.py, heatmap.py, debug_stream.py, calibrate.py
├── jobs/                         # fetch_neis.py, fetch_news.py, mock_feed.py, rollup.py(→insights.db), report.py(→reports.db), llm.py, translators.py, newsbody.py
├── static/                       # index.html(셸), css/{base,screens,insight}.css, js/{core,floor,wait,room,week,today,news}.js, manifest.json, sw.js
├── data/                         # queue.db, insights.db, reports.db, admin.db, meal.json, news.json, positions.json (git 제외) / 포함: plan_bg.png, nutrition_std.json, carbon_std.json, news_feeds.json, zones.json
├── deploy/                       # mealboard-{api,mock,vision,admin,neis,news,rollup,report}.service, *.timer, sudoers-mealboard, cloudflared-config.yml(견본)
├── tests/                        # test_waittime.py 등 순수 로직 테스트
├── .env.example                  # 키 이름만 (실제 .env는 git 제외)
├── .gitignore                    # data/*(예외 2개), .env, .venv/, __pycache__/, *.db*
└── pyproject.toml                # uv 관리
```

**파일 명명 규칙 (Plant 레포 계승)** — 접두어가 실행 주체를 뜻한다:
- `run_*` = systemd가 자동 실행 / `setup_*`, `calibrate_*` = 사람이 최초 1회 / `check_*` = 검증 도구 / 무접두어 = 라이브러리
- 설정의 단일 출처는 파일 하나(`data/zones.json`(git 추적, 관리 앱만 쓴다), `data/nutrition_std.json`, `.env`) — **스크립트에 좌표·키·기준치 하드코딩 금지**

## 4. 개발 환경 규칙

- 패키지 관리는 **uv**. 시스템 Python 3.13 사용(`requires-python >=3.11`). Pi에서는 반드시 `uv venv --system-site-packages`를 **`uv sync`/`uv add`보다 먼저** 실행
  (picamera2는 시스템 apt 패키지. 순서가 뒤바뀌면 venv 재생성으로 설치분이 날아감 — Plant 프로젝트에서 실증된 함정)
- 개발 PC에는 카메라가 없다 → `jobs/mock_feed.py`로 SQLite에 가짜 데이터를 넣고 app/과 static/을 개발한다.
  vision/ 없이 웹 전체가 돌아가는 상태를 항상 유지할 것
- **mock과 vision은 동시에 켜지지 않는다** — `mealboard-mock.service`의 `Conflicts=mealboard-vision.service`가 보장. 학교 Pi 전환 = mock disable, vision enable
- API 계약이 우선: `/api/status`, `/api/history`, `/api/meal`, `/api/heatmap` 응답 스키마를 바꿀 때는
  프론트·문서·mock을 같은 커밋에서 함께 수정. `/api/status`의 `state`는 `ok | no_data | insufficient_rate`, 2분 이상 새 행 없으면 `stale`
- `static/sw.js`는 정적 파일만 캐시. **`/api/*`는 절대 캐시하지 않는다**(폴링이 무의미해짐)
- `.env`는 systemd `EnvironmentFile`로도 읽히므로 **값 뒤 줄 끝 주석 금지**(값의 일부로 들어감)
- 모듈 실행은 저장소 루트에서 `python -m jobs.mock_feed` 형식(패키지 import 경로 유지)

## 5. SSH로 Pi를 제어할 때 (Claude Code 필독)

접속: `ssh <PI_USER>@<PI_HOST>` (실제 값은 .env 또는 사용자에게 확인. known_hosts 이슈 시 사용자에게 보고)
팀원은 각자 계정 + SSH 키. 공용 계정 없음.

**허용 (자유롭게)**
- 읽기 전체: `systemctl status`, `journalctl -u <svc> -n 100`, DB SELECT, `ls`, `cat`, `ss -tlnp`, `vcgencmd measure_temp`, `timedatectl`
- 코드 반영: `/opt/mealboard`에서 `git pull` 후 해당 서비스만 `sudo systemctl restart mealboard-api`(vision·mock은 아래 주의 참조). 의존성이 바뀌면 `uv sync`, 유닛이 바뀌면 `bash setup_pi.sh`

**주의 (실행 전 사용자에게 확인)**
- `mealboard-vision` 재시작: 점심 운영 시간(11:30~14:00)에는 카운팅 공백이 생긴다 — 시간을 확인하고 물을 것
- 카메라는 **배타적 자원**: calibrate.py·디버그 도구를 띄우려면 vision 서비스를 먼저 내려야 한다 (Plant 프로젝트 실증)
- systemd 유닛 수정, cloudflared 설정 변경, apt 설치, 타임존 변경(Plant 타이머 시각에 영향)
- sudoers 드롭인(`/etc/sudoers.d/mealboard`) 설치·변경, `tailscale serve` 설정 변경. **`tailscale serve reset`·`funnel reset` 은 절대 실행하지 않는다**(공개 Funnel 443 까지 함께 지워진다)

**금지 (사용자 명시 지시 없이는 절대 불가)**
- `/opt/mealboard` 안에서 파일 직접 편집 — 코드는 PC에서 커밋해 pull한다
- `data/` 내 파일 삭제·초기화, DB의 DELETE/DROP/UPDATE — 정리 도구를 만들 때는 반드시 ①빈 조건이면 실행 거부 ②실행 전 `queue.db.bak-<시각>` 자동 백업 ③되돌리는 명령 출력, 세 겹을 갖출 것 (Plant 프로젝트에서 `--fix`로 220행을 잃은 사고의 재발 방지 규칙)
- `~/plant/` 및 Plant 유닛(planthub·plantdash·plantsnap) 접근·수정
- 프레임 이미지를 디스크에 저장하거나 외부로 전송하는 코드 작성 — 어떤 디버깅 목적이라도 사용자 승인 필요(승인된 예외는 §2 영상 취급·디버그 뷰 행뿐)
- `rm -rf`, 전원 관련(`shutdown`, `reboot`) — reboot는 확인 후에만
- .env, 인증키, 터널 자격증명(`~/.cloudflared/*.json`, `/etc/cloudflared/config.yml`)을 로그·커밋·채팅에 노출

**진단 순서 (뭔가 이상할 때)**
① `git status`·`git log -1`(코드가 최신인가) → ② 서비스 살아있나 → ③ DB에 최신 행이 들어오나 → ④ journalctl → ⑤ 시간 동기·온도·디스크.
"대시보드에 안 나온다"는 대부분 그리는 쪽 문제다: DB에 데이터가 있으면 프론트/라우터부터 의심 (Plant 실증)

## 6. Git / GitHub 워크플로

- 원격: `github.com/xparapx/Mealboard_Demo` (main 단일 브랜치, 선행 레포와 동일). GitHub 조작은 `gh` CLI(설치·로그인은 사용자가)
- 커밋 단위: 기능 하나 = 커밋 하나. 메시지는 한국어 명령형 요약 한 줄 + 필요 시 본문
  (예: `vision: 라인크로싱 완충띠 ±20px 추가`)
- **커밋 전 확인**: `git status`에 data/(.gitignore 예외 5개 제외)·.env가 없을 것 (있다면 .gitignore부터 수정)
- 코드와 매뉴얼 동기화: `<pre>` 수록 코드를 바꾼 커밋은 docs/manual.html도 같은 커밋에서 갱신,
  `check_manual.py`류 대조 도구가 생기면 커밋 전 실행
- push는 매 작업 세션 종료 시. 사용자가 요청하면 중간에도. Pi는 자동으로 pull하지 않는다 — 배포는 사람(또는 `/deploy`)이 명시적으로
- README 「작업 로그」는 의미 있는 변경마다 갱신 (커밋마다는 아님)

## 7. Claude Code 확장 요소 (필요한 것만)

- **CLAUDE.md(이 파일)로 충분한 것**: 프로젝트 규칙·구조·안전수칙 전달 — 별도 에이전트/플러그인 불필요
- **슬래시 커맨드 (권장, `.claude/commands/`)**: 반복 절차를 파일로 고정
  - `pi-status.md` — SSH로 서비스 상태(api·mock/vision·neis.timer·cloudflared) + DB 최신 행 시각 + 디스크·온도·시간동기 요약
  - `deploy.md` — 커밋 확인 → push → Pi에서 pull → (필요 시 uv sync) → api 서비스 재시작 → `/api/status` 응답 검증
  - `logday.md` — 오늘 journalctl 요약과 이상 징후 보고
- **스킬 (후순위)**: docs/manual.html 패널 편집 규칙(용어 즉시 설명, 복사 버튼, 코드 동기화)이
  반복 부담이 되면 그때 `manual-editing` 스킬로 분리 — 초기엔 만들지 말 것
- **서브에이전트/훅**: 이 규모에서는 불필요. 도입하지 않는다
- **MCP**: 불필요 (GitHub는 gh/git CLI, Pi는 ssh로 충분)

## 8. 단계별 로드맵 (현재 위치를 커밋 로그와 README 작업 로그로 판단)

① app/ + mock_feed + /api/status → /docs에서 검증
② static/ 대시보드 (mock 데이터로 완성. 레이아웃은 docs/ 도면의 스펙을 따른다)
③ jobs/fetch_neis.py + /api/meal (파싱 + 영양 지표 3종)
④ vision/ 프로토타입 — 개발 PC 웹캠·동영상 파일 소스로 counter·zones·waittime 검증 (tests/ 포함). `vision/source.py`로 소스 추상화
⑤ Pi 이전: uv 셋업(§4 순서 엄수) → systemd → 외부 공개(Tailscale Funnel) **[홈 Pi에서 완료]** → calibrate → 실측 **[학교 Pi]**
⑥ PWA + QR (공개 주소는 ⑤의 Funnel. 정식 배포 시 Cloudflare Tunnel + 유료 도메인으로 전환)
⑦ (선택) 해석 LLM, 히트맵 고도화, AI HAT 도입
⑧ **확장(진행 중, `docs/PLAN-2026-09.md`)**: 집계 DB·인사이트 API → 5화면 프론트 → 관리 앱 → 로컬 LLM·기사 요약 → 문서

각 단계는 독립 실행 가능해야 하며, 다음 단계로 넘어가기 전 사용자에게 동작 확인을 받는다.
