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
STALE_SEC = 120                             # 이 시간 넘게 새 행·새 파일이 없으면 '데이터 없음' (status·positions·집계 커버리지 공통)
ROLLUP_WINDOW = _choice("ROLLUP_WINDOW", "lunch", ("lunch", "all"))   # 집계 창 (스테이징 mock 은 종일 돌므로 all)
FEED_SOURCE = _choice("FEED_SOURCE", "vision", ("mock", "vision"))    # 집계 행의 출처 표기

# 관리 앱 (tailnet 전용, 별도 프로세스). 허용목록이 비면 tailnet 경로는 닫히고, 로컬 키가 비면 SSH 터널 경로도 닫힌다 (fail-closed)
ADMIN_PORT = int(os.getenv("ADMIN_PORT", "8101"))
ADMIN_USERS = os.getenv("ADMIN_USERS", "")            # Tailscale 로그인, 쉼표 구분 — app/admin/auth.parse_users 가 정리
ADMIN_LOCAL_KEY = os.getenv("ADMIN_LOCAL_KEY", "")    # SSH 터널(127.0.0.1) 경로용. 생성: openssl rand -hex 16
DEBUG_PORT = int(os.getenv("DEBUG_PORT", "8102"))     # vision 디버그 MJPEG (127.0.0.1 전용, 관리 앱이 중계)
RUN_DIR = Path(os.getenv("RUN_DIR", str(DATA / "run")))   # 메타데이터 소켓 디렉터리 (Pi: /run/mealboard)
ADMIN_DB_PATH = DATA / "admin.db"                     # 쓰기 주체: 관리 앱 (감사 로그)
