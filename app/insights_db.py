"""읽기 전용 SQLite 연결 — insights.db · reports.db · (집계가 읽는) queue.db. 공개 app 은 SELECT 만 한다 (CLAUDE.md §2).
파일이 없으면 None — 만들지 않는다. 만드는 쪽은 jobs/rollup.py · jobs/report.py · vision/mock 뿐이다.
파일은 있는데 표가 없으면(만들다 만 파일, 0바이트 복원) 역시 None — 라우터가 no_data 로 답하게."""
import sqlite3

from .config import INSIGHTS_DB_PATH, REPORTS_DB_PATH


def connect_ro(path=INSIGHTS_DB_PATH, table="lunch_days"):
    if not path.exists():
        return None
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone():
        con.close()
        return None
    return con


def connect_reports_ro():
    return connect_ro(REPORTS_DB_PATH, "reports")


def meta(con):
    """insights.db 의 meta 표 {key: value} — 집계 창·출처·인기 기준값. 표가 없으면 {}"""
    try:
        return {k: v for k, v in con.execute("SELECT key, value FROM meta")}     # Row 든 tuple 이든
    except sqlite3.OperationalError:
        return {}
