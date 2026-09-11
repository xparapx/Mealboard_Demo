"""queue.db 에서 더미(mock) 표본을 걷어내는 정리 도구 — CLAUDE.md §5 의 세 겹 규칙을 따른다.
  ① 조건이 비면(지울 행이 0) 실행을 거부한다   ② 실행 전 queue.db.bak-<시각> 을 자동으로 만든다   ③ 되돌리는 명령을 출력한다

표본에는 출처 열이 없다(samples 는 숫자만). 그래서 '실측이 시작된 시각' 을 경계로 그 이전 행을 더미로 본다(09-11: Pi 는 17:35 부터 vision 실측).
--before 없이 실행하면 아무것도 하지 않고 분포만 보여 준다(dry run).

  uv run python -m jobs.purge_mock                                   # 날짜별 행 수만 출력
  uv run python -m jobs.purge_mock --before 2026-09-11T17:35 --yes  # 그 시각 이전 samples·zone_samples·cell_samples 삭제(백업 뒤)

VACUUM 으로 파일도 줄인다(200 MB → 수 MB). 되돌리기: 출력된 cp 명령 한 줄."""
import argparse
import datetime as dt
import shutil
import sqlite3
import sys

from app.config import DB_PATH

TABLES = ("samples", "zone_samples", "cell_samples")


def counts(con, before=None):
    out = {}
    for t in TABLES:
        out[t] = con.execute(f"SELECT COUNT(*) FROM {t}" + (" WHERE ts < ?" if before else ""), (before,) if before else ()).fetchone()[0]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", help="이 시각(ISO, 로컬) 이전 표본을 더미로 보고 지운다. 없으면 분포만 출력")
    ap.add_argument("--yes", action="store_true", help="실제로 지운다(없으면 계획만)")
    a = ap.parse_args()
    if not DB_PATH.exists():
        print(f"{DB_PATH} 가 없다"); return 1
    con = sqlite3.connect(DB_PATH)
    print("날짜별 samples 행 수(최근 10일):")
    for d, n, mx in con.execute("SELECT substr(ts,1,10), COUNT(*), MAX(queue_len) FROM samples GROUP BY 1 ORDER BY 1 DESC LIMIT 10"):
        print(f"  {d}  {n:>8} 행  최대 대기 {mx}")
    if not a.before:
        print("\n--before <시각> 을 주면 그 이전 행을 지울 계획을 보여 준다(--yes 로 실행)"); return 0
    try:
        dt.datetime.fromisoformat(a.before)
    except ValueError:
        print(f"--before 는 ISO 시각이어야 한다: {a.before!r}"); return 2
    plan = counts(con, a.before)
    total = sum(plan.values())
    print(f"\n{a.before} 이전:  " + "  ".join(f"{t} {n}" for t, n in plan.items()))
    if total == 0:                                                   # ① 빈 조건 거부
        print("지울 행이 없다 — 아무것도 하지 않는다"); return 0
    keep = counts(con)["samples"] - plan["samples"]
    print(f"남는 samples: {keep} 행")
    if not a.yes:
        print("\n계획만 보였다. 실행하려면 --yes"); return 0
    con.close()
    bak = DB_PATH.with_name(f"{DB_PATH.name}.bak-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(DB_PATH, bak)                                       # ② 자동 백업(WAL 이 있으면 체크포인트 뒤 복사)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    shutil.copy2(DB_PATH, bak)
    with con:
        for t in TABLES:
            con.execute(f"DELETE FROM {t} WHERE ts < ?", (a.before,))
    con.execute("VACUUM")
    after = counts(con)
    con.close()
    print(f"\n삭제 완료  남은 행: " + "  ".join(f"{t} {n}" for t, n in after.items()))
    print(f"백업: {bak}")
    print(f"되돌리기:  sudo systemctl stop mealboard-vision && cp {bak} {DB_PATH} && sudo systemctl start mealboard-vision")   # ③
    return 0


if __name__ == "__main__":
    sys.exit(main())
