"""insights.db · reports.db 읽기 전용 연결. 공개 app 은 SELECT 만 한다 (CLAUDE.md §2 '파일당 쓰기 주체 하나').
파일이 없으면 None — 만들지 않는다. 만드는 쪽은 jobs/rollup.py · jobs/report.py 뿐이다."""
import sqlite3

from .config import INSIGHTS_DB_PATH, REPORTS_DB_PATH


def connect_ro(path=INSIGHTS_DB_PATH):
    if not path.exists():
        return None
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def connect_reports_ro():
    return connect_ro(REPORTS_DB_PATH)
