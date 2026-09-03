"""급식 시간창과 5분 구간 — 순수 함수. DB·시계를 모른다.
평소 곡선(typical)·집계(rollup)·인사이트 API 가 같은 규칙으로 시각을 자르도록 한 곳에 둔다.
시각 단위는 '자정부터 분'(minute of day, 0~1439) — SQLite strftime('%H')*60+strftime('%M') 과 같은 눈금이다.
.env 의 LUNCH_START·LUNCH_END 는 이 모듈을 import 하는 순간 검증된다 — 잘못된 값은 서비스 시작을 막는다(요청 때 500 이 아니라)."""
import datetime as dt

from .config import LUNCH_START, LUNCH_END

BUCKET_MIN = 5          # 5분 단위로 묶는다. 30초 폴링 노이즈를 지우고 곡선을 읽히게
DAY_MIN = 24 * 60
WINDOWS = ("lunch", "all")


def parse_hhmm(text):
    """'11:30' → 690. 형식·범위가 어긋나면 ValueError — .env 오타를 조용히 넘기지 않는다"""
    try:
        h, m = (int(v) for v in str(text).strip().split(":"))
    except ValueError:
        raise ValueError(f"HH:MM 형식이 아니다: {text!r}") from None
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"시각 범위를 벗어난다: {text!r}")
    return h * 60 + m


def lunch_bounds(start=LUNCH_START, end=LUNCH_END):
    """급식 시간창 [lo, hi) 를 '자정부터 분'으로. 기본값은 .env 의 LUNCH_START~LUNCH_END"""
    lo, hi = parse_hhmm(start), parse_hhmm(end)
    if lo >= hi:
        raise ValueError(f"LUNCH_START({start}) 는 LUNCH_END({end}) 보다 앞서야 한다")
    return lo, hi


def bounds(window):
    """집계 창. lunch = 급식 시간창, all = 하루 전체(스테이징 mock 은 종일 돌기 때문에)"""
    if window == "all":
        return 0, DAY_MIN
    if window == "lunch":
        return lunch_bounds()
    raise ValueError(f"ROLLUP_WINDOW 는 lunch|all 중 하나: {window!r}")


def _as_dt(t):
    return dt.datetime.fromisoformat(t) if isinstance(t, str) else t


def seconds_of_day(t):
    """ISO 문자열 또는 datetime → 자정부터 초(소수 포함). 이웃 표본 간격을 잴 때 쓴다"""
    t = _as_dt(t)
    return t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6


def minute_of_day(t):
    return int(seconds_of_day(t) // 60)


def bin_of(t):
    """표본이 속한 5분 구간의 시작 분. 12:03 → 720(12:00), 12:05 → 725. /api/typical 의 minute_of_day 와 같은 눈금"""
    return minute_of_day(t) // BUCKET_MIN * BUCKET_MIN


def in_window(t, lo, hi):
    """[lo, hi) 안의 시각인가 (분 단위, 끝은 열린 구간)"""
    return lo <= minute_of_day(t) < hi


def iso_at(date, sec):
    """'2026-09-03' + 자정부터 초 → 'YYYY-MM-DDTHH:MM:SS'. 하루 끝(86400)은 23:59:59 로 눌러 T24:00:00 이 나오지 않게"""
    sec = min(int(sec), DAY_MIN * 60 - 1)
    return f"{date}T{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def weekday_of(date):
    """'YYYY-MM-DD' 또는 date → 요일 번호. SQLite strftime('%w') 규칙(0=일요일) — lunch_days.weekday 와 같은 눈금"""
    d = dt.date.fromisoformat(date) if isinstance(date, str) else date
    return (d.weekday() + 1) % 7


LUNCH_LO, LUNCH_HI = lunch_bounds()     # import 시점 검증. 잘못된 .env 는 여기서 ValueError
