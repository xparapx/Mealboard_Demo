"""queue.db 연결. 쓰기는 mock_feed(또는 vision) 하나뿐, app 은 SELECT 만 한다.
samples 와 zone_samples 는 같은 시각(ts)에 한 트랜잭션으로 들어온다 — 어느 한쪽만 남는 표본이 없게."""
import sqlite3
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
  ts           TEXT PRIMARY KEY,   -- ISO 8601 로컬시각
  queue_len    INTEGER,            -- L : 대기 인원
  rate_per_min REAL,               -- λ : 배식대 통과율 (RATE_WINDOW_SEC 이동합, 명/분)
  wait_min     REAL,               -- 공표 대기 = 원시 W × 보정 K (보정 전이면 원시 그대로. 산출 불가면 NULL)
  state        TEXT NOT NULL,      -- ok | no_data | insufficient_rate
  wait_raw_min     REAL,           -- 원시 W = L / λ (09-16 자동 보정 B안 — 수동 실측 대조용으로 원시도 남긴다)
  measured_wait_min REAL,          -- 자동 실측: ROI 진입→λ선 통과 체류시간의 이동 창 중앙값(분). 개인 값은 저장하지 않는다
  calib        REAL                -- 보정계수 K = median(실측/진입 시점 예측), 0.5~3.0. 실측이 모자라면 NULL
);
CREATE TABLE IF NOT EXISTS zone_samples (
  ts   TEXT    NOT NULL,           -- samples.ts 와 같은 시각
  zone TEXT    NOT NULL,           -- data/zones.json 의 zones[].id
  n    INTEGER NOT NULL,           -- 그 순간 구역 안 인원수. 숫자만 — 개별 좌표는 남기지 않는다 (CLAUDE.md §2)
  PRIMARY KEY (ts, zone)
);
CREATE TABLE IF NOT EXISTS cell_samples (
  ts   TEXT    NOT NULL,           -- samples.ts 와 같은 시각
  cell INTEGER NOT NULL,           -- vision/zones.py 격자(GRID_COLS × GRID_ROWS) 셀 번호 = row * cols + col
  n    INTEGER NOT NULL,           -- 그 순간 셀 안 인원수(0 인 셀은 쓰지 않는다). 최근 30분 밀집도 히트맵의 재료 — 숫자만
  PRIMARY KEY (ts, cell)
);
"""


def connect():
    con = sqlite3.connect(DB_PATH, timeout=5)
    con.execute("PRAGMA journal_mode=WAL")   # 읽기와 쓰기가 서로 막지 않게
    con.executescript(SCHEMA)                # 없으면 만들고, 있으면 그대로
    # 09-16 자동 보정 B안: 기존 파일에 새 열을 더한다(추가만 — DELETE/UPDATE 없음). 옛 행은 NULL
    have = {r[1] for r in con.execute("PRAGMA table_info(samples)")}
    for col in ("wait_raw_min REAL", "measured_wait_min REAL", "calib REAL"):
        if col.split()[0] not in have:
            con.execute(f"ALTER TABLE samples ADD COLUMN {col}")
    con.commit()
    con.row_factory = sqlite3.Row
    return con
