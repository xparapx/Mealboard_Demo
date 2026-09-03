"""감사 로그 — data/admin.db 의 유일한 writer 는 관리 앱이다 (CLAUDE.md §2). 모든 변경 요청(재시작·작업 실행·스트림 on/off·구역 저장)과
lockdown 전환이 한 행씩 남는다: 누가(user·via), 언제, 무엇을, 결과."""
import asyncio
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
    con.execute("PRAGMA synchronous=NORMAL")     # WAL 이면 앱이 죽어도 안전, fsync 는 체크포인트 때만 — SD 카드에서 커밋마다 수십 ms 를 아낀다
    con.executescript(SCHEMA)
    con.row_factory = sqlite3.Row
    return con


def _write(row):
    con = connect()
    try:
        con.execute("INSERT INTO admin_log (ts, user, via, action, target, detail, ok, ip) VALUES (?,?,?,?,?,?,?,?)", row)
        con.commit()
    finally:
        con.close()


def log(user, action, target=None, detail=None, ok=True, ip=None):
    """user 는 auth.identify 가 준 {'user','via'} 또는 None(시스템 — 워치독).
    이벤트 루프 위에서 불리면(SSE 구독·릴레이·타이머) 디스크 쓰기를 스레드로 넘긴다 — 루프가 fsync 를 기다리며 프레임 전달을 멈추지 않게.
    루프 밖(동기 라우터·잡)에서는 그 자리에서 쓴다. 순서는 같은 스레드풀 큐라 사실상 보존된다"""
    row = (dt.datetime.now().isoformat(timespec="seconds"), (user or {}).get("user"), (user or {}).get("via"),
           action, target, detail, int(bool(ok)), ip)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        _write(row)
    else:
        loop.run_in_executor(None, _write, row)


def recent(n=50):
    con = connect()
    try:
        return [dict(r) for r in con.execute("SELECT * FROM admin_log ORDER BY id DESC LIMIT ?", (min(max(n, 1), 500),))]
    finally:
        con.close()
