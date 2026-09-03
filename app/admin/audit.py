"""감사 로그 — data/admin.db 의 유일한 writer 는 관리 앱이다 (CLAUDE.md §2). 모든 변경 요청(재시작·작업 실행·스트림 on/off·구역 저장)과
lockdown 전환이 한 행씩 남는다: 누가(user·via), 언제, 무엇을, 결과."""
import datetime as dt
import sqlite3

from ..config import ADMIN_DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, user TEXT, via TEXT,
  action TEXT NOT NULL, target TEXT, detail TEXT, ok INTEGER NOT NULL, ip TEXT
);
"""


def connect():
    con = sqlite3.connect(ADMIN_DB_PATH, timeout=5)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    con.row_factory = sqlite3.Row
    return con


def log(user, action, target=None, detail=None, ok=True, ip=None):
    """user 는 auth.identify 가 준 {'user','via'} 또는 None(시스템 — 워치독)"""
    con = connect()
    try:
        con.execute("INSERT INTO admin_log (ts, user, via, action, target, detail, ok, ip) VALUES (?,?,?,?,?,?,?,?)",
                    (dt.datetime.now().isoformat(timespec="seconds"), (user or {}).get("user"), (user or {}).get("via"),
                     action, target, detail, int(bool(ok)), ip))
        con.commit()
    finally:
        con.close()


def recent(n=50):
    con = connect()
    try:
        return [dict(r) for r in con.execute("SELECT * FROM admin_log ORDER BY id DESC LIMIT ?", (min(max(n, 1), 500),))]
    finally:
        con.close()
