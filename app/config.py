"""설정의 단일 출처. 경로와 .env 값은 여기서만 읽는다."""
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

API_PORT = int(os.getenv("API_PORT", "8100"))
LUNCH_START = os.getenv("LUNCH_START", "11:30")
LUNCH_END = os.getenv("LUNCH_END", "14:00")
STALE_SEC = 120                             # 이 시간 넘게 새 행·새 파일이 없으면 '데이터 없음' (status·positions·집계 커버리지 공통)
ROLLUP_WINDOW = os.getenv("ROLLUP_WINDOW", "lunch")   # lunch | all — 집계 창 (스테이징 mock 은 종일 돌므로 all)
FEED_SOURCE = os.getenv("FEED_SOURCE", "vision")      # mock | vision — 집계 행의 출처 표기
