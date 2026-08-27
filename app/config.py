"""설정의 단일 출처. 경로와 .env 값은 여기서만 읽는다."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent      # 저장소 루트
load_dotenv(BASE / ".env")

DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
DB_PATH = DATA / "queue.db"
MEAL_JSON = DATA / "meal.json"

API_PORT = int(os.getenv("API_PORT", "8100"))
LUNCH_START = os.getenv("LUNCH_START", "11:30")
LUNCH_END = os.getenv("LUNCH_END", "14:00")
