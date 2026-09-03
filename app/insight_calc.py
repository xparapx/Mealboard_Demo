"""인사이트 집계의 순수 계산. DB·시계·파일을 모른다.
하루 단위 집계(jobs/rollup.py)와 /api/insight/day 의 오늘 즉석 계산(basis: live)이 같은 함수를 쓴다.

입력 표본은 queue.db samples 행을 dict 로 만든 것 — {ts, queue_len, rate_per_min, wait_min, state}, ts 오름차순.
구역 행은 zone_samples 의 {ts, zone, n}. 시각 눈금(자정부터 분·5분 구간)은 app.lunch 를 따른다.
판정 규칙은 docs/PLAN-2026-09.md §2.3 — 바꾸면 CALC_VERSION 을 올린다(옛 집계와 구분하기 위해).
"""
import re
import statistics

from .config import STALE_SEC
from .lunch import BUCKET_MIN, iso_at, seconds_of_day
from vision.waittime import MIN_RATE

CALC_VERSION = 1
GOLDEN_WAIT = 3.0          # 분. 이 이하면 '지금 가면 바로 먹는다'
GOLDEN_MIN = 5             # 황금 구간은 이만큼 연속돼야 인정
BOTTLENECK_QUEUE = 5       # 줄이 이만큼 서 있는데
BOTTLENECK_RATIO = 0.5     # 처리율이 평소의 절반 아래(또는 산출 불가)이면 병목
BOTTLENECK_N = 3           # 병목은 표본 3개·2분 이상 이어져야 한다(한 프레임의 흔들림을 걸러낸다)
BOTTLENECK_MIN = 2
_ALLERGY = re.compile(r"\s*[(（]\s*[\d.,\s]+\s*[)）]\s*$")        # "(1.5.6)"  — static/index.html splitAllergy 와 같은 규칙
_TRAIL = re.compile(r"\s+\d{1,2}(?:\.\d{1,2})+\.?\s*$")           # " 1.5.6."  (괄호 없이 붙는 경우)


# ---- 작은 도구 -----------------------------------------------------------------

def _mean(xs, nd=2):
    return round(sum(xs) / len(xs), nd) if xs else None


def _sec(s):
    """표본의 자정부터 초. day_summary 가 한 번 계산해 s['sec'] 에 넣어 두므로 문자열을 거듭 파싱하지 않는다"""
    return s["sec"] if "sec" in s else seconds_of_day(s["ts"])


def _windowed(samples, lo, hi):
    """[lo, hi) 분 안의 표본만, 각 표본에 'sec' 를 채워서"""
    out = []
    for s in samples:
        sec = _sec(s)
        if lo * 60 <= sec < hi * 60:
            s["sec"] = sec
            out.append(s)
    return out


def _runs(samples, pred, min_minutes=0, min_n=1):
    """pred 를 만족하는 표본이 끊기지 않고(간격 ≤ STALE_SEC) 이어진 구간들. 각 구간은 표본 리스트"""
    runs, cur = [], []
    for s in samples:
        ok = pred(s)
        if ok and (not cur or _sec(s) - _sec(cur[-1]) <= STALE_SEC):
            cur.append(s)
            continue
        if cur:
            runs.append(cur)
        cur = [s] if ok else []
    if cur:
        runs.append(cur)
    return [r for r in runs if len(r) >= min_n and (_sec(r[-1]) - _sec(r[0])) / 60 >= min_minutes]


def _event(kind, run, value, detail):
    return {"kind": kind, "start_ts": run[0]["ts"], "end_ts": run[-1]["ts"],
            "minutes": round((_sec(run[-1]) - _sec(run[0])) / 60, 1), "value": value, "detail": detail}


# ---- 구간 통계 ----------------------------------------------------------------

def bin_samples(samples):
    """5분 구간별 통계 — lunch_bins 한 행씩. bin 은 구간 시작 분(app.lunch.bin_of 와 같은 눈금)"""
    groups = {}
    for s in samples:
        groups.setdefault(int(_sec(s) // 60) // BUCKET_MIN * BUCKET_MIN, []).append(s)
    out = []
    for b in sorted(groups):
        g = groups[b]
        waits = [s["wait_min"] for s in g if s["wait_min"] is not None]
        queues = [s["queue_len"] for s in g if s["queue_len"] is not None]
        rates = [s["rate_per_min"] for s in g if s["rate_per_min"] is not None]
        out.append({"bin": b, "n": len(g),
                    "ok_n": sum(s["state"] == "ok" for s in g),
                    "insufficient_n": sum(s["state"] == "insufficient_rate" for s in g),
                    "avg_queue": _mean(queues, 1), "max_queue": max(queues, default=None),
                    "avg_rate": _mean(rates), "avg_wait": _mean(waits, 1), "max_wait": max(waits, default=None)})
    return out


def bin_zones(zone_rows, lo=0, hi=24 * 60):
    """구역별 5분 구간 통계 — zone_bins 한 행씩. 입력은 {ts, zone, n} (숫자뿐, 좌표 없음). 창 밖은 버린다"""
    groups = {}
    for r in zone_rows:
        m = int(seconds_of_day(r["ts"]) // 60)
        if lo <= m < hi:
            groups.setdefault((m // BUCKET_MIN * BUCKET_MIN, r["zone"]), []).append(r["n"])
    return [{"bin": b, "zone": z, "n": len(ns), "avg_n": _mean(ns), "max_n": max(ns)}
            for (b, z), ns in sorted(groups.items())]


# ---- 판정 -------------------------------------------------------------------

def coverage(samples, date, lo, hi, now_sec=None):
    """측정 품질. 창 [lo, hi) 분 안에서 화면이 '데이터 없음'을 띄웠을 시간 = 창 시작·표본들·창 끝을 차례로 놓고
    이웃 간격마다 STALE_SEC 를 넘긴 초과분의 합(표본 뒤 STALE_SEC 동안은 화면이 마지막 값을 보여준다).
    오늘이면 now_sec 까지만 잰다(아직 오지 않은 시간은 빈 시간이 아니다). 창 밖 표본은 여기서 걸러낸다."""
    start, end = lo * 60, hi * 60
    if now_sec is not None:
        end = min(end, now_sec)
    if end <= start:
        return {"coverage_pct": None, "stale_min": 0.0, "gaps": []}
    edges = [start] + [s["sec"] for s in _windowed(samples, lo, hi)] + [end]
    gaps, stale = [], 0.0
    for a, b in zip(edges, edges[1:]):
        excess = b - a - STALE_SEC
        if excess > 0:
            stale += excess
            gaps.append({"start_ts": iso_at(date, a + STALE_SEC), "end_ts": iso_at(date, b), "minutes": round(excess / 60, 1)})
    return {"coverage_pct": round(100 * (1 - stale / (end - start)), 1), "stale_min": round(stale / 60, 1), "gaps": gaps}


def served_estimate(samples):
    """처리 인원 추정 = Σ λ × min(표본 간격, STALE_SEC). 데이터가 끊긴 동안은 세지 않는다"""
    total = 0.0
    for a, b in zip(samples, samples[1:]):
        if b["rate_per_min"] is not None:
            total += b["rate_per_min"] * min(_sec(b) - _sec(a), STALE_SEC) / 60
    return round(total)


def typical_rate(samples):
    """평소 처리율 = 줄이 있고(≥5) 산출이 된 표본들의 λ 중앙값. 없으면 None"""
    rates = [s["rate_per_min"] for s in samples
             if s["state"] == "ok" and (s["queue_len"] or 0) >= BOTTLENECK_QUEUE and s["rate_per_min"] is not None]
    return round(statistics.median(rates), 2) if rates else None


def golden_windows(samples):
    """황금 구간: ok ∧ 대기 ≤3분 ∧ λ ≥ 0.5 가 5분 이상 연속. value = 평균 대기"""
    def ok(s):
        return s["state"] == "ok" and s["wait_min"] is not None and s["wait_min"] <= GOLDEN_WAIT \
            and (s["rate_per_min"] or 0) >= MIN_RATE
    out = []
    for r in _runs(samples, ok, GOLDEN_MIN):
        avg = _mean([s["wait_min"] for s in r], 1)
        out.append(_event("golden", r, avg, f"평균 대기 {avg}분"))
    return out


def golden_bins(points, key="forecast_wait"):
    """5분 구간 점들({minute_of_day, key}) 에서 대기 ≤ GOLDEN_WAIT 가 GOLDEN_MIN 이상 이어진 구간 [{start_min, end_min}].
    예보 곡선처럼 표본이 아니라 구간 값만 있을 때 쓴다 — 문턱은 golden_windows 와 같다"""
    out, cur = [], []

    def flush():
        if cur and cur[-1]["minute_of_day"] + BUCKET_MIN - cur[0]["minute_of_day"] >= GOLDEN_MIN:
            out.append({"start_min": cur[0]["minute_of_day"], "end_min": cur[-1]["minute_of_day"] + BUCKET_MIN})
    for p in points:
        good = p.get(key) is not None and p[key] <= GOLDEN_WAIT
        if good and cur and p["minute_of_day"] - cur[-1]["minute_of_day"] == BUCKET_MIN:
            cur.append(p)
            continue
        flush()
        cur = [p] if good else []
    flush()
    return out


def bottlenecks(samples, typical=None):
    """병목: 줄 ≥5 인데 산출 불가이거나 λ 가 평소의 절반 아래 — 표본 3개·2분 이상. value = 최대 대기 인원"""
    typical = typical if typical is not None else typical_rate(samples)

    def stuck(s):
        if (s["queue_len"] or 0) < BOTTLENECK_QUEUE:
            return False
        if s["state"] == "insufficient_rate":
            return True
        return bool(typical) and s["rate_per_min"] is not None and s["rate_per_min"] < BOTTLENECK_RATIO * typical
    out = []
    for r in _runs(samples, stuck, BOTTLENECK_MIN, BOTTLENECK_N):
        rate = _mean([s["rate_per_min"] for s in r if s["rate_per_min"] is not None], 1)
        peak = max(s["queue_len"] for s in r)
        out.append(_event("bottleneck", r, peak, f"처리 {rate}/분 (평소 {typical}/분), 최대 {peak}명 대기"))
    return out


def insufficient_runs(samples):
    """λ 부족으로 산출 불가였던 구간들(길이 무관). 합이 insufficient_min"""
    return [_event("insufficient", r, len(r), f"표본 {len(r)}개")
            for r in _runs(samples, lambda s: s["state"] == "insufficient_rate")]


def rise_rate(bins):
    """줄이 불어나는 최대 속도(명/분) — 이웃한 5분 구간의 평균 대기 인원 차이. 인기 메뉴일수록 가파르다"""
    best = None
    for a, b in zip(bins, bins[1:]):
        if a["avg_queue"] is None or b["avg_queue"] is None or b["bin"] - a["bin"] != BUCKET_MIN:
            continue
        slope = (b["avg_queue"] - a["avg_queue"]) / BUCKET_MIN
        best = slope if best is None else max(best, slope)
    return round(max(best, 0.0), 2) if best is not None else None


def normalize_menu(raw):
    """NEIS 메뉴명 정제 — 알레르기 번호·별표·군더더기 공백을 뗀다. 같은 메뉴가 날마다 같은 키가 되게"""
    s = str(raw).strip()
    s = _ALLERGY.sub("", s)
    s = _TRAIL.sub("", s)
    s = re.sub(r"[*#]", "", s)
    return re.sub(r"\s+", " ", s).strip(" .,·")


def popularity(rise, peak_wait, base_rise, base_wait):
    """인기 지수 = 100·(0.5·rise/base_rise + 0.5·peak_wait/base_wait). 기준(base)이 없는 항은 빼고 남은 항으로 평균"""
    terms = []
    if base_rise and rise is not None:
        terms.append(rise / base_rise)
    if base_wait and peak_wait is not None:
        terms.append(peak_wait / base_wait)
    return round(100 * sum(terms) / len(terms)) if terms else None


def median_or_none(xs, nd=2):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), nd) if xs else None


# ---- 하루 요약 -----------------------------------------------------------------

def day_summary(samples, date, lo, hi, now_sec=None):
    """하루(또는 오늘 지금까지)의 요약 — lunch_days 한 행 + bins + events(황금·병목·빈 시간·산출 불가, 시각순).
    창 밖 표본은 여기서 걸러낸다"""
    samples = _windowed(samples, lo, hi)
    cov = coverage(samples, date, lo, hi, now_sec)
    bins = bin_samples(samples)
    typical = typical_rate(samples)
    golden = golden_windows(samples)
    bott = bottlenecks(samples, typical)
    insuff = insufficient_runs(samples)
    stale = [{"kind": "stale", "start_ts": g["start_ts"], "end_ts": g["end_ts"], "minutes": g["minutes"],
              "value": g["minutes"], "detail": "데이터 없음"} for g in cov["gaps"]]
    waits = [s for s in samples if s["wait_min"] is not None]
    queues = [s for s in samples if s["queue_len"] is not None]
    peak_w = max(waits, key=lambda s: s["wait_min"], default=None)
    peak_q = max(queues, key=lambda s: s["queue_len"], default=None)
    return {
        "date": date, "window_lo": lo, "window_hi": hi, "n_samples": len(samples),
        "coverage_pct": cov["coverage_pct"], "stale_min": cov["stale_min"],
        "insufficient_min": round(sum(e["minutes"] for e in insuff), 1),
        "first_ts": samples[0]["ts"] if samples else None, "last_ts": samples[-1]["ts"] if samples else None,
        "peak_wait": peak_w["wait_min"] if peak_w else None, "peak_wait_ts": peak_w["ts"] if peak_w else None,
        "peak_queue": peak_q["queue_len"] if peak_q else None, "peak_queue_ts": peak_q["ts"] if peak_q else None,
        "avg_wait": _mean([s["wait_min"] for s in waits], 1),
        "served_est": served_estimate(samples), "typical_rate": typical, "rise_rate": rise_rate(bins),
        "golden_min": round(sum(e["minutes"] for e in golden), 1),
        "bottleneck_min": round(sum(e["minutes"] for e in bott), 1),
        "calc_version": CALC_VERSION,
        "events": sorted(golden + bott + stale + insuff, key=lambda e: e["start_ts"]),
        "bins": bins,
    }


# ---- 최근 30분 밀집도 (09-03 사용자 요청) ----------------------------------------------------
def density(cell_sums, ticks, cols, rows):
    """{cell: 창 안 인원수 합} + 표본 틱 수 → 셀 목록 [{i, avg, w}]. avg 는 틱당 평균 인원, w 는 최댓값을 1 로 한 진하기(0~1).
    합이 0 인 셀은 뺀다. 개별 위치가 아니라 셀 단위 합계이므로 사람을 되짚을 수 없다"""
    if not cell_sums or ticks <= 0:
        return []
    top = max(cell_sums.values())
    out = []
    for i, s in sorted(cell_sums.items()):
        if s <= 0 or not (0 <= int(i) < cols * rows):
            continue
        out.append({"i": int(i), "avg": round(s / ticks, 2), "w": round(s / top, 3)})
    return out
