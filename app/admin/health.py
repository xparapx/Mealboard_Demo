"""Pi 건강 상태 — CLAUDE.md §5 진단 순서(코드가 최신인가 → 서비스 → DB 최신 행 → 로그 → 시간·온도·디스크)를 카드 한 장으로.
전부 읽기만 한다. 개발 PC 에서는 없는 항목이 None 으로 나온다."""
import datetime as dt
import shutil
import subprocess

from ..config import BASE, DB_PATH, DATA
from ..insights_db import connect_ro

POSITIONS = DATA / "positions.json"


def _age(ts):
    try:
        return round((dt.datetime.now() - dt.datetime.fromisoformat(ts)).total_seconds())
    except (TypeError, ValueError):
        return None


def db_age():
    """queue.db 마지막 표본의 나이(초). 파일이 없으면 None"""
    con = connect_ro(DB_PATH, "samples")
    if con is None:
        return None
    try:
        row = con.execute("SELECT ts FROM samples ORDER BY ts DESC LIMIT 1").fetchone()
        return _age(row["ts"]) if row else None
    finally:
        con.close()


def positions_age():
    try:
        return round(dt.datetime.now().timestamp() - POSITIONS.stat().st_mtime)
    except OSError:
        return None


def disk():
    u = shutil.disk_usage(BASE)
    return {"free_gb": round(u.free / 1e9, 1), "used_pct": round(100 * u.used / u.total)}


def temp_c():
    try:
        return round(int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000, 1)
    except (OSError, ValueError):
        return None


def uptime_s():
    try:
        return round(float(open("/proc/uptime").read().split()[0]))
    except (OSError, ValueError):
        return None


def _cmd(argv):
    try:
        p = subprocess.run(list(argv), capture_output=True, text=True, timeout=5)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def ntp_synced():
    out = _cmd(("timedatectl", "show", "-p", "NTPSynchronized", "--value"))
    return None if out is None else out == "yes"


def git_head():
    return _cmd(("git", "-C", str(BASE), "rev-parse", "--short", "HEAD"))


def snapshot():
    return {"db_age_s": db_age(), "positions_age_s": positions_age(), "disk": disk(), "temp_c": temp_c(),
            "uptime_s": uptime_s(), "ntp": ntp_synced(), "git": git_head(),
            "now": dt.datetime.now().isoformat(timespec="seconds")}
