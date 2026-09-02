"""queue.db 연결. 쓰기는 mock_feed(또는 vision) 하나뿐, app 은 SELECT 만 한다.
samples 와 zone_samples 는 같은 시각(ts)에 한 트랜잭션으로 들어온다 — 어느 한쪽만 남는 표본이 없게."""
import sqlite3
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
  ts           TEXT PRIMARY KEY,   -- ISO 8601 로컬시각
  queue_len    INTEGER,            -- L : 대기 인원
  rate_per_min REAL,               -- λ : 배식대 통과율 (5분 이동평균, 명/분)
  wait_min     REAL,               -- W = L / λ  (산출 불가면 NULL)
  state        TEXT NOT NULL       -- ok | no_data | insufficient_rate
);
CREATE TABLE IF NOT EXISTS zone_samples (
  ts   TEXT    NOT NULL,           -- samples.ts 와 같은 시각
  zone TEXT    NOT NULL,           -- data/zones.json 의 zones[].id
  n    INTEGER NOT NULL,           -- 그 순간 구역 안 인원수. 숫자만 — 개별 좌표는 남기지 않는다 (CLAUDE.md §2)
  PRIMARY KEY (ts, zone)
);
"""


def connect():
    con = sqlite3.connect(DB_PATH, timeout=5)
    con.execute("PRAGMA journal_mode=WAL")   # 읽기와 쓰기가 서로 막지 않게
    con.executescript(SCHEMA)                # 없으면 만들고, 있으면 그대로
    con.row_factory = sqlite3.Row
    return con
