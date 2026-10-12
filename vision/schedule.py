"""수집 시간창 — 순수 함수. 설정 파일도 시계도 모른다(값은 app/lunch.py 가 .env 에서 묶어 준다).

급식은 하루 세 번 창이 열린다(09-04 운영 규칙): 3학년 점심 11:20~12:30 · 1·2학년 점심 12:30~13:40 · 석식.
석식은 날에 따라 둘(10-12 사용자 규칙): 평일 17:30~18:30, **금요일·휴일 전날 17:00~18:00** — '휴일 전날' 판정은 is_eve(내일이 급식 없는 날인가).
카메라 노드(vision)는 이 창 안에서만 사람을 세고 기록한다. 창 밖에서는 추론도 기록도 멈춘다(09-11: 더미 곡선을 쓰지 않는다 —
화면은 '지금은 급식 시간이 아닙니다 · 다음 창' 안내를 띄운다). 공개 API 는 같은 창으로 '지금 값이 실측인가'(feed.live) 를 판정한다.

.env 표기:  MEAL_WINDOWS=11:30-12:30 3학년 점심;12:30-13:30 1·2학년 점심;17:30-18:30 석식
  항목은 ';' 로 나누고, 항목은 'HH:MM-HH:MM' 뒤에 공백과 라벨(생략 가능, 기본 '급식'). 창은 겹칠 수 없고 자정을 넘길 수 없다.
시각 단위는 app/lunch.py 와 같은 '자정부터 분'(0~1439)."""
import datetime as dt
from collections import namedtuple

MealWindow = namedtuple("MealWindow", "lo hi label")     # [lo, hi) 분, 라벨
DAY_MIN = 24 * 60
DEFAULT_TEXT = "11:20-12:30 3학년 점심;12:30-13:40 1·2학년 점심;17:30-18:30 석식"       # 평일(09-11 시작 앞당김 · 09-16 중식 끝 13:40 · 10-12 석식 17:30~18:30)
DEFAULT_EVE_TEXT = "11:20-12:30 3학년 점심;12:30-13:40 1·2학년 점심;17:00-18:00 석식"   # 금요일·휴일 전날(10-12 사용자 규칙: 석식 30분 앞당김)


def _hhmm(text):
    try:
        h, m = (int(v) for v in text.strip().split(":"))
    except ValueError:
        raise ValueError(f"HH:MM 형식이 아니다: {text!r}") from None
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"시각 범위를 벗어난다: {text!r}")
    return h * 60 + m


def parse_windows(text):
    """'11:30-12:30 3학년 점심;…' → 시작 순으로 정렬된 MealWindow 목록. 빈 문자열은 빈 목록(창 없음 = 언제나 더미).
    형식 오류·역순·겹침은 ValueError — .env 오타를 조용히 넘기지 않는다(서비스 시작을 막는다)"""
    out = []
    for item in str(text or "").split(";"):
        item = item.strip()
        if not item:
            continue
        span, _, label = item.partition(" ")
        if "-" not in span:
            raise ValueError(f"'HH:MM-HH:MM 라벨' 형식이 아니다: {item!r}")
        a, b = span.split("-", 1)
        lo, hi = _hhmm(a), _hhmm(b)
        if lo >= hi:
            raise ValueError(f"시작이 끝보다 앞서야 한다(자정을 넘길 수 없다): {item!r}")
        out.append(MealWindow(lo, hi, label.strip() or "급식"))
    out.sort()
    for p, n in zip(out, out[1:]):
        if n.lo < p.hi:
            raise ValueError(f"창이 겹친다: {p.label} {p.lo}~{p.hi} 와 {n.label} {n.lo}~{n.hi}")
    return out


def _as_date(d):
    if isinstance(d, dt.datetime):
        return d.date()
    if isinstance(d, str):
        return dt.date.fromisoformat(d[:10])
    return d


def parse_dates(text):
    """'2026-10-02,2026-12-24' → {date, …}. 빈 값은 빈 집합. 형식 오류는 ValueError(.env 오타를 조용히 넘기지 않는다)"""
    out = set()
    for item in str(text or "").replace(";", ",").split(","):
        item = item.strip()
        if item:
            out.add(dt.date.fromisoformat(item))
    return out


def is_eve(date, meal_dates=(), eve_dates=()):
    """'금요일·휴일 전날' 인가(10-12 사용자 규칙) = **내일이 급식 없는 날**인가.
    판정 순서: ① eve_dates(.env MEAL_EVE_DATES, 'YYYY-MM-DD' — 캐시가 못 보는 먼 휴일의 전날을 손으로 지정)에 오늘이 있으면 참
    ② 내일이 NEIS 캐시(meal_dates, 'YYYYMMDD') 범위 안이면 캐시에 없을 때 참(공휴일·시험일 반영)
    ③ 범위 밖이면 내일이 주말일 때 참(금요일). 캐시는 보통 이번 주뿐이라 다음 주 월요일 휴일의 전날(금)은 ③ 으로도 잡힌다."""
    today = _as_date(date)
    if today in set(eve_dates or ()):
        return True
    tomorrow = today + dt.timedelta(days=1)
    known = {dt.date.fromisoformat(f"{d[:4]}-{d[4:6]}-{d[6:8]}") for d in meal_dates if len(d) == 8 and d.isdigit()}
    if known and tomorrow <= max(known):
        return tomorrow not in known
    return tomorrow.weekday() >= 5


def pick(date, normal, eve, meal_dates=(), eve_dates=()):
    """그날의 수집 창 목록 — 휴일 전날이면 eve, 아니면 normal"""
    return eve if is_eve(date, meal_dates, eve_dates) else normal


def should_record(window, source):
    """카메라 노드가 지금 표본을 써야 하는가 — 창이 열려 있고(window 가 MealWindow) 출처가 vision 일 때만.
    창 밖에서는 아무 행도 쓰지 않는다(옛 더미 곡선 없음). FEED_SOURCE=mock 이면 카메라 노드는 쓰지 않는다 — 더미는 mock 유닛의 몫(Conflicts 로 배타)"""
    return window is not None and source == "vision"


def current(windows, minute):
    """자정부터 분 → 지금 열린 창, 없으면 None. 끝은 열린 구간([lo, hi))"""
    for w in windows:
        if w.lo <= minute < w.hi:
            return w
    return None


def next_after(windows, minute):
    """자정부터 분 → (다음에 열릴 창, 며칠 뒤) . 지금 열린 창은 세지 않는다(그 다음 창을 찾는다).
    오늘 남은 창이 없으면 내일의 첫 창 (days=1). 창이 하나도 없으면 None.

    예: 창 [11:30~12:30, 12:30~13:30, 17:30~18:30]
        09:00 → (11:30 창, 0)   12:00(3학년 점심 중) → (12:30 창, 0)   19:00 → (11:30 창, 1)
    """
    if not windows:
        return None
    for w in windows:                 # 정렬돼 있으니 시작이 아직 안 온 첫 창이 곧 다음 창(지금 열린 창은 lo <= minute 라 건너뛴다)
        if w.lo > minute:
            return w, 0
    return windows[0], 1              # 오늘 남은 창이 없다 → 내일 첫 창


def describe(w):
    """API·화면용 dict. None 은 그대로 None"""
    return None if w is None else {"label": w.label, "lo": w.lo, "hi": w.hi}
