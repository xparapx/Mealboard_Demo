"""설정의 단일 출처. 경로와 .env 값은 여기서만 읽는다. 값이 허용 범위 밖이면 시작 자체를 막는다(요청 때 500 이 되지 않게)."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent      # 저장소 루트
load_dotenv(BASE / ".env")

DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
DB_PATH = DATA / "queue.db"                 # 쓰기 주체: vision(또는 mock)
INSIGHTS_DB_PATH = DATA / "insights.db"     # 쓰기 주체: jobs/rollup.py
REPORTS_DB_PATH = DATA / "reports.db"       # 쓰기 주체: jobs/report.py
MEAL_JSON = DATA / "meal.json"
ZONES_JSON = DATA / "zones.json"            # git 템플릿. Pi 보정값은 같은 폴더의 미추적 zones.local.json (vision/zones.py 가 overlay)


def _choice(name, default, allowed):
    v = os.getenv(name, default)
    if v not in allowed:
        raise SystemExit(f".env {name}={v!r} — {'|'.join(allowed)} 중 하나여야 한다")
    return v


API_PORT = int(os.getenv("API_PORT", "8100"))
LUNCH_START = os.getenv("LUNCH_START", "11:30")     # 형식 검증은 app/lunch.py 가 import 시점에 한다
LUNCH_END = os.getenv("LUNCH_END", "14:00")
# 수집 시간창 세 개(09-04 운영 규칙): 카메라 노드는 이 창 안에서만 세고, 창 밖은 더미 곡선 + 화면 '더미데이터' 띠. 형식·겹침 검증은 vision/schedule.py (app/lunch.py import 시점)
MEAL_WINDOWS = os.getenv("MEAL_WINDOWS", "11:30-12:30 3학년 점심;12:30-13:30 1·2학년 점심;17:30-18:30 석식")
STALE_SEC = 120                             # 이 시간 넘게 새 행·새 파일이 없으면 '데이터 없음' (status·positions·집계 커버리지 공통)
ROLLUP_WINDOW = _choice("ROLLUP_WINDOW", "lunch", ("lunch", "all"))   # 집계 창 (스테이징 mock 은 종일 돌므로 all)
FEED_SOURCE = _choice("FEED_SOURCE", "vision", ("mock", "vision"))    # 집계 행의 출처 표기

# 관리 앱 (tailnet 전용, 별도 프로세스). 허용목록이 비면 tailnet 경로는 닫히고, 로컬 키가 비면 SSH 터널 경로도 닫힌다 (fail-closed)
ADMIN_PORT = int(os.getenv("ADMIN_PORT", "8101"))
ADMIN_USERS = os.getenv("ADMIN_USERS", "")            # Tailscale 로그인, 쉼표 구분 — app/admin/auth.parse_users 가 정리
ADMIN_LOCAL_KEY = os.getenv("ADMIN_LOCAL_KEY", "")    # SSH 터널(127.0.0.1) 경로용. 생성: openssl rand -hex 16
DEBUG_PORT = int(os.getenv("DEBUG_PORT", "8102"))     # vision 디버그 MJPEG (127.0.0.1 전용, 관리 앱이 중계)
# 카메라 카운팅 노드 (vision/counter.py, 로드맵 ④). 홈 Pi 에서는 picamera 금지(Plant 카메라와 배타) — webcam:N | file:경로 만
VIDEO_SOURCE = os.getenv("VIDEO_SOURCE", "picamera")   # picamera | webcam:0 | file:경로
VISION_SIZE = os.getenv("VISION_SIZE", "2304x1296")     # 카메라 요청 해상도. imx708 은 2304x1296 이 센서 전체(2×2 비닝) — 1536x864 는 중앙 크롭이라 화각이 2/3 로 준다(09-04 실측)
VISION_FPS = float(os.getenv("VISION_FPS", "5"))        # 추론 목표 fps (Pi 5 CPU 의 yolo11n 640 은 3~5)
VISION_IMGSZ = int(os.getenv("VISION_IMGSZ", "640"))
VISION_CONF = float(os.getenv("VISION_CONF", "0.35"))
YOLO_WEIGHTS = os.getenv("YOLO_WEIGHTS", str(DATA / "models" / "yolo11n.pt"))   # ultralytics 가중치. Hailo hef 백엔드는 다음 단계
RUN_DIR = Path(os.getenv("RUN_DIR", str(DATA / "run")))   # 메타데이터 소켓 디렉터리 (Pi: /run/mealboard)
META_UDP_PORT = 8103                                  # AF_UNIX 가 없는 개발 PC(Windows)의 메타데이터 폴백 — UDP 127.0.0.1 (Pi 에서는 쓰지 않는다)
DEBUG_FLAG = Path("/tmp/debug_on") if os.name != "nt" else RUN_DIR / "debug_on"   # MJPEG 켜짐 계약 파일 (vision 과 공유, PrivateTmp 금지)
ADMIN_DB_PATH = DATA / "admin.db"                     # 쓰기 주체: 관리 앱 (감사 로그)
LLM_HEF = os.getenv("LLM_HEF", "")                    # 로컬 LLM(Hailo-10H GenAI) .hef 경로. 빈 값 = LLM 없음 → 모든 소비자가 규칙 템플릿·DeepL 로 폴백
LLM_REPORT = os.getenv("LLM_REPORT", "0") == "1"      # 리포트(아침 예보·점심 결산)에도 LLM 을 쓸지. 09-04 스파이크: 1.5B 모델은 한국어 문장이 무너지고 영어로도 사실을 지어내
                                                      # 규칙 템플릿이 낫다 — 기본 0(템플릿). 한국어가 되는 모델이 오면 1
