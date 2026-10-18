"""심사위원 구동 경로(10-18, 점검서 N3) — Pi·카메라 없이 노트북에서 한 줄로 전체 화면을 띄운다.

    uv run python -m jobs.demo                 # 모의 데이터 8주치 생성 → 포트 8800 에 공개 앱 + 브라우저 열기
    uv run python -m jobs.demo --with-admin    # 관리 앱(8801)도 함께(보정 편집기·시스템 탭) — 주소에 로컬 키가 붙어 터미널에 찍힌다
    uv run python -m jobs.demo --generate-only # 데이터만 만들고 끝(검증용)
    옵션: --port 8800 · --data data/demo · --keep(기존 데이터 유지) · --no-browser · --anchor 2026-10-14T12:38:00

운영·개발 데이터(data/)와 **완전히 분리된 폴더**(기본 data/demo/, git 제외)에 queue.db·insights.db·reports.db·meal.json·news.json·
positions.json·zones.local.json 을 만든다. 생성은 결정론적(날짜가 난수 씨앗)이라 누가 켜도 같은 화면이 나온다.

가상 시계(app/clock.py, .env DEMO_CLOCK): 기본 기준 **2026-10-14(수) 12:44** — 1·2학년 점심 피크 한가운데(인기 메뉴 날, 줄 60명·약 7분). 켠 순간부터 실제 시간이 흐르고,
이 모듈의 피더 스레드가 그 시각의 표본을 10초마다 queue.db·positions.json 에 이어 쓴다(카메라 노드의 대역 — 기록 함수는 vision/record.py 와 같은 SQL).

모의 급식실 모델(값은 모두 '그럴 법한' 수준이며 실측이 아니다 — 화면 안내 띠·앱 안내 탭이 '모의 데이터' 를 명시한다):
  3학년 점심 11:20~12:30 약 190명 · 1·2학년 점심 12:30~13:40 약 400명 · 석식 평일 17:30~18:30(금·휴일 전날 17:00~18:00) 약 130명
  도착 = 수업 종료 뒤 두 번의 몰림(가우스 혼합) + 잔잔한 유입, 인기 메뉴일수록 초반에 더 몰린다(menu factor) · 배식 속도 μ ≈ 9.5명/분(2줄)
  병목 = 며칠에 한 번 배식이 4~6분 평소의 ⅓ 로 느려짐(오늘은 11:30~11:35 — 병목 로그에 보이게) · 자동 실측 보정 K ≈ 1.0~1.2 · 추석(09-24·25)·한글날(10-09) 급식 없음
집계·리포트는 실제 코드(jobs/rollup.py 의 함수, jobs/report.py run) 그대로 돌린다 — 화면이 보여 주는 통계·예보·리포트는 모의 표본에서 '진짜로' 계산된 값이다.
"""
import argparse
import datetime as dt
import json
import math
import os
import random
import secrets
import shutil
import sqlite3
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ANCHOR = "2026-10-14T12:44:00"
WEEKS = 8
TICK = 10                       # 표본 간격(초) — vision 의 10초 표본과 같다
COARSE_TICK = 30                # 7일보다 오래된 날은 30초(표본만, 위치 없음) — 생성 시간·용량
HOLIDAYS = {"2026-09-24", "2026-09-25", "2026-10-09"}      # 추석 연휴 · 한글날(2026)
LUNCH_WAVES = ((11 * 60 + 20, 12 * 60 + 30, 190), (12 * 60 + 30, 13 * 60 + 40, 400))
DINNER_N = 130
MU_LUNCH, MU_DINNER = 9.5, 5.5  # 배식 속도(명/분)
PATH = [(0.08, 0.97), (0.05, 0.30), (0.10, 0.07), (0.55, 0.05)]      # 줄의 동선(출입문 → 창가 통로 → 배식대 앞, mock_feed 와 같다)
TABLES1 = [(x, y) for x in (0.26, 0.49, 0.72) for y in (0.17, 0.28, 0.39, 0.50)]     # 1구역 좌석(배식대 가까운 쪽) 식탁 중심
TABLES2 = [(x, y) for x in (0.26, 0.49, 0.72) for y in (0.62, 0.73, 0.84, 0.95)]
SEATS = 280

# 메뉴(알레르기 번호는 NEIS 표기) · kcal · 탄단지 에너지 비율 · 인기 계수(1.0 = 보통, 클수록 초반에 몰린다)
MENUS = [
    (["등심돈가스 (1.2.5.6.10.12.13)", "친환경쌀밥", "우동국 (1.5.6.13)", "양배추샐러드 (1.5.13)", "배추김치 (9)", "요구르트 (2)"], 1045, (0.60, 0.16, 0.24), 1.25),
    (["치킨마요덮밥 (1.5.6.13.15)", "친환경현미밥", "미소된장국 (5.6)", "단무지무침", "배추김치 (9)", "사과주스"], 1010, (0.61, 0.15, 0.24), 1.22),
    (["제육볶음 (5.6.10.13)", "친환경쌀밥", "콩나물국 (5)", "상추쌈·쌈장 (5.6)", "깍두기 (9)", "바나나"], 980, (0.58, 0.19, 0.23), 1.12),
    (["닭갈비 (5.6.13.15)", "친환경흑미밥", "미역국 (5.6)", "감자채볶음", "배추김치 (9)", "우유 (2)"], 965, (0.57, 0.20, 0.23), 1.10),
    (["소불고기 (5.6.13.16)", "친환경쌀밥", "된장국 (5.6)", "시금치나물", "배추김치 (9)", "방울토마토 (12)"], 1005, (0.56, 0.21, 0.23), 1.15),
    (["짜장면 (5.6.10.13)", "탕수육 (5.6.10.12.13)", "단무지", "배추김치 (9)", "식혜"], 1120, (0.63, 0.13, 0.24), 1.20),
    (["김치볶음밥 (5.9.10.13)", "계란후라이 (1)", "어묵국 (1.5.6.13)", "브로콜리초장 (5.6.13)", "요구르트 (2)"], 905, (0.60, 0.14, 0.26), 0.98),
    (["고등어구이 (7)", "친환경쌀밥", "무된장국 (5.6)", "호박나물", "배추김치 (9)", "귤"], 890, (0.58, 0.21, 0.21), 0.82),
    (["순두부찌개 (5.6.9.13)", "친환경보리밥", "오이무침 (5.6.13)", "김구이", "깍두기 (9)", "우유 (2)"], 870, (0.60, 0.18, 0.22), 0.80),
    (["카레라이스 (2.5.6.10.12.13)", "친환경쌀밥", "유부장국 (5.6)", "단무지", "배추김치 (9)", "파인애플"], 1015, (0.64, 0.13, 0.23), 1.05),
    (["비빔밥 (1.5.6.13.16)", "미소국 (5.6)", "군만두 (5.6.10.13)", "배추김치 (9)", "수박"], 960, (0.60, 0.16, 0.24), 1.02),
    (["닭볶음탕 (5.6.13.15)", "친환경쌀밥", "콩나물무침 (5)", "김치전 (5.6.9)", "배추김치 (9)", "요구르트 (2)"], 1030, (0.56, 0.20, 0.24), 1.08),
    (["돼지갈비찜 (5.6.10.13)", "친환경쌀밥", "북어국 (1.5.6)", "무생채", "배추김치 (9)", "포도"], 1060, (0.55, 0.21, 0.24), 1.18),
    (["오징어볶음 (5.6.13.17)", "친환경현미밥", "계란국 (1.5.9)", "도라지무침 (5.6.13)", "배추김치 (9)", "우유 (2)"], 920, (0.59, 0.19, 0.22), 0.90),
    (["잔치국수 (1.5.6.13)", "김밥 (1.2.5.6.10.13)", "단무지", "배추김치 (9)", "바나나"], 940, (0.66, 0.12, 0.22), 0.95),
    (["치즈함박스테이크 (1.2.5.6.10.12.13.16)", "친환경쌀밥", "크림스프 (1.2.5.6)", "코울슬로 (1.5.13)", "배추김치 (9)", "오렌지"], 1110, (0.57, 0.16, 0.27), 1.24),
]
DINNERS = [
    (["참치김치찌개 (5.6.9.13)", "친환경쌀밥", "계란말이 (1)", "배추김치 (9)"], 760, (0.58, 0.20, 0.22)),
    (["닭강정 (5.6.13.15)", "친환경쌀밥", "콩나물국 (5)", "깍두기 (9)"], 820, (0.57, 0.18, 0.25)),
    (["볶음우동 (1.5.6.10.13)", "유부장국 (5.6)", "단무지", "요구르트 (2)"], 790, (0.63, 0.13, 0.24)),
    (["두부조림 (5.6.13)", "친환경현미밥", "미역국 (5.6)", "배추김치 (9)"], 700, (0.60, 0.19, 0.21)),
    (["오므라이스 (1.2.5.6.10.12.13)", "친환경쌀밥", "맑은국", "배추김치 (9)"], 810, (0.60, 0.14, 0.26)),
]
TODAY_MENU = 0                  # 오늘(기준일)은 가장 인기인 돈가스 — '줄이 길어지는 메뉴' 1위가 오늘과 맞물린다
NEWS = {                        # 이슈피드 샘플 — 공개 참고 자료(실존 페이지)에 대한 짧은 자체 설명. 번역·AI 요약 표시는 붙이지 않는다(그런 과정이 없었으므로)
    "climate": [
        {"source": "IPCC", "date": "참고 자료", "link": "https://www.ipcc.ch/report/ar6/syr/", "title": "IPCC 제6차 평가보고서 종합 — 1.5℃ 를 지키려면 이 10년이 결정적",
         "summary": "기후변화에 관한 정부간 협의체의 종합 보고서. 지금의 배출 추세와 남은 탄소예산, 부문별 감축 선택지를 정리한다. 급식 잔반 줄이기도 식품 부문 감축의 한 조각이다."},
        {"source": "UNEP", "date": "참고 자료", "link": "https://www.unep.org/resources/publication/food-waste-index-report-2024", "title": "UNEP 음식물 쓰레기 지수 보고서 2024",
         "summary": "유엔환경계획이 가정·외식·소매 단계의 음식물 쓰레기를 나라별로 추정한 보고서. 학교 급식의 잔반 측정·공개가 왜 의미 있는지 배경이 된다."},
        {"source": "NASA", "date": "참고 자료", "link": "https://climate.nasa.gov/", "title": "NASA 기후 변화 — 지표로 보는 지구",
         "summary": "이산화탄소 농도·지구 평균기온·해수면·빙하 질량 같은 핵심 지표를 최신 관측값으로 보여 주는 공개 페이지."},
    ],
    "tech": [
        {"source": "Raspberry Pi", "date": "참고 자료", "link": "https://www.raspberrypi.com/products/raspberry-pi-5/", "title": "Raspberry Pi 5 — 이 대시보드가 도는 손바닥 컴퓨터",
         "summary": "Mealboard 의 카메라 노드·웹 서버·집계가 전부 이 보드 한 대에서 돈다. 영상은 메모리에서만 처리되고 숫자만 남는다."},
        {"source": "Ultralytics", "date": "참고 자료", "link": "https://docs.ultralytics.com/models/yolo11/", "title": "YOLO11 — 사람을 세는 실시간 객체 검출 모델",
         "summary": "급식실 카메라 프레임에서 '사람' 상자를 찾아 ByteTrack 으로 이어 붙인다. 대기 인원 L 과 배식대 통과(λ)가 여기서 나온다."},
        {"source": "FastAPI", "date": "참고 자료", "link": "https://fastapi.tiangolo.com/", "title": "FastAPI — 공개 API 와 관리 앱의 뼈대",
         "summary": "/api/status 같은 JSON 응답을 내는 파이썬 웹 프레임워크. 단일 파이썬 스택으로 카메라 노드와 언어를 통일했다."},
    ],
}
KEYWORDS = [["급식", 14], ["대기시간", 12], ["잔반", 9], ["탄소", 9], ["카메라", 8], ["Raspberry Pi", 7], ["YOLO11", 6], ["기후", 6], ["음식물 쓰레기", 5],
            ["FastAPI", 4], ["영양", 4], ["IPCC", 4], ["UNEP", 3], ["NASA", 3], ["알레르기", 3], ["평면도", 2]]


# ---------------- 순수 모델 (설정·DB·시계를 모른다) ----------------

def rng_for(date, salt=""):
    return random.Random(f"mealboard-demo:{date}:{salt}")


def poisson(r, lam):
    """작은 λ 의 포아송 표본(Knuth) — 표준 라이브러리만"""
    if lam <= 0:
        return 0
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        k += 1
        p *= r.random()
        if p <= L:
            return k - 1


def school_days(anchor_date, weeks=WEEKS):
    """기준일 주의 월요일에서 weeks-1 주 전 월요일 ~ 기준일까지의 평일, 공휴일 제외"""
    monday = anchor_date - dt.timedelta(days=anchor_date.weekday())
    start = monday - dt.timedelta(weeks=weeks - 1)
    out, d = [], start
    while d <= anchor_date:
        if d.weekday() < 5 and d.isoformat() not in HOLIDAYS:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def menu_index(date, anchor_date=None):
    """그날 중식 메뉴 번호 — 기준일(오늘)만 TODAY_MENU 로 고정(가장 인기인 메뉴 → 피크가 선명하게), 나머지는 씨앗 난수"""
    if anchor_date is not None and date == anchor_date:
        return TODAY_MENU
    return rng_for(date, "menu").randrange(len(MENUS))


def is_eve(date, days):
    """내일이 급식 없는 날인가(금요일·휴일 전날 → 석식 17:00~18:00). days 는 급식 있는 날 집합"""
    return (date + dt.timedelta(days=1)) not in days


def waves_for(date, days, anchor_date=None):
    """그날의 창들: (lo, hi, N, mu, kind, f). 인기 계수 f 는 그날 메뉴의 것(meal.json 과 같은 메뉴). 석식은 휴일 전날이면 30분 앞"""
    f = MENUS[menu_index(date, anchor_date)][3]
    out = [(lo, hi, n, MU_LUNCH, "lunch", f) for lo, hi, n in LUNCH_WAVES]
    dlo = 17 * 60 if is_eve(date, days) else 17 * 60 + 30
    out.append((dlo, dlo + 60, DINNER_N, MU_DINNER, "dinner", 1.0))
    return out


def arrivals_per_min(m, D, n, f, kind="lunch"):
    """창 시작 뒤 m 분의 도착률(명/분). 두 번의 몰림(수업 종료 — 학급이 많을수록 흩어져 온다) + 잔잔한 유입. 인기(f)가 크면 첫 몰림이 더 좁고 높다.
    석식은 몰림이 느슨하다(자율학습 사이에 흩어져 온다)"""
    if kind == "dinner":
        sd1, sd2, w1, w2 = 7.0, 9.0, 0.45, 0.30
    else:
        t = min(1.0, max(0.0, (n - 190) / 210))                           # 190명(3학년) → 400명(1·2학년): 학급이 많을수록 몰림이 퍼진다
        sd1, sd2, w1, w2 = (3.2 + 3.8 * t) / f, 5.5 + 2.0 * t, 0.55 - 0.20 * t, 0.30
    g = lambda mu, sd: math.exp(-((m - mu) / sd) ** 2 / 2) / (sd * math.sqrt(2 * math.pi))
    body = w1 * g(7, sd1) + w2 * g(21, sd2)
    flat = (1 - w1 - w2) / max(1, D - 15) if m < D - 15 else 0.0
    return n * (body + flat)


def bottleneck_for(date, lo, hi, kind, anchor_date):
    """배식이 거의 멈추는 구간 [시작분, 끝분) 또는 None. 오늘(기준일) 3학년 창은 12:03~12:08 고정, 다른 날은 30% 확률로 창 중간쯤"""
    if date == anchor_date and kind == "lunch" and lo == LUNCH_WAVES[0][0]:
        return (11 * 60 + 30, 11 * 60 + 35)
    r = rng_for(date, f"bott{lo}")
    if kind == "lunch" and r.random() < 0.18:
        s = lo + r.randint(8, 30)
        return (s, s + r.randint(4, 6))
    return None


def _points(r, queue, seated):
    """익명 바닥 좌표: 줄은 동선(PATH)을 따라 등간격, 식사 중은 식탁 중심 주변. 좌표뿐 — 사람을 식별할 정보는 만들 수도 없다"""
    seg = [math.dist(PATH[i], PATH[i + 1]) for i in range(len(PATH) - 1)]
    total = sum(seg)
    pts = []
    for i in range(queue):
        d = (i + 0.5) / max(1, queue) * total * min(1.0, 0.25 + queue / 40)     # 줄이 짧으면 배식대 가까이 몰려 선다
        k = 0
        while k < len(seg) - 1 and d > seg[k]:
            d -= seg[k]
            k += 1
        t = d / seg[k]
        x = PATH[k][0] + (PATH[k + 1][0] - PATH[k][0]) * t + r.uniform(-0.02, 0.02)
        y = PATH[k][1] + (PATH[k + 1][1] - PATH[k][1]) * t + r.uniform(-0.02, 0.02)
        pts.append({"x": round(min(max(x, 0), 1), 3), "y": round(min(max(y, 0), 1), 3)})
    for i in range(seated):
        tables = TABLES1 if r.random() < 0.68 else TABLES2                      # 배식대 가까운 1구역을 더 좋아한다
        cx, cy = r.choice(tables)
        pts.append({"x": round(min(max(cx + r.uniform(-0.07, 0.07), 0), 1), 3), "y": round(min(max(cy + r.uniform(-0.035, 0.035), 0), 1), 3)})
    return pts


def simulate_wave(date, lo, hi, n, mu, kind, f, anchor_date, tick=TICK, with_points=True):
    """한 창의 표본 틱 목록 [{sec, queue, rate, wait, state, raw, measured, k, served_n, pts}]. 결정론적(날짜·창이 씨앗).
    λ 는 180초 이동합(명/분), 공표 대기는 90초 중앙값 × 그날의 보정계수 K(자동 실측의 자리) — vision/counter 의 평활·보정 계약을 흉내낸다"""
    from vision.waittime import estimate_wait
    r = rng_for(date, f"wave{lo}")
    mu_day = mu * min(1.12, max(0.88, r.gauss(1.0, 0.05)))
    k_day = round(min(1.25, max(0.92, r.gauss(1.06, 0.05))), 2)
    bott = bottleneck_for(date, lo, hi, kind, anchor_date)
    D = hi - lo
    queue, served_log, raw_log, q_log, recent_served, acc = 0, [], [], [], [], 0.0
    out = []
    for sec in range(lo * 60, hi * 60, tick):
        m = (sec - lo * 60) / 60
        cap = mu_day * (0.35 + 0.65 * min(1.0, m / 3))                     # 첫 3분은 배식이 느리게 시작한다
        if bott and bott[0] <= m + lo < bott[1]:
            cap *= 0.38                                                        # 배식이 평소의 ⅓ 로 — 병목 판정(평소의 절반 아래) 에 걸리되 W 가 폭주하진 않게
        queue += poisson(r, arrivals_per_min(m, D, n, f, kind) * tick / 60)
        acc += cap * tick / 60 * r.gauss(1.0, 0.15)                           # 배식은 포아송보다 고르다(두 줄이 쉬지 않고 돈다) — 누적분의 정수만 통과
        served = min(queue, max(0, int(acc)))
        acc -= served
        acc = min(acc, 3.0)                                                    # 줄이 비면 여유를 쌓아 두지 않는다
        queue -= served
        served_log.append((sec, served))
        served_log = [(s, c) for s, c in served_log if s > sec - 180]
        rate = round(sum(c for _, c in served_log) / 3.0, 2)
        q_log = (q_log + [queue])[-3:]
        q_pub = sorted(q_log)[len(q_log) // 2]                                # 25초 중앙값(세 틱)
        raw, state = estimate_wait(q_pub, rate)
        raw_log = (raw_log + [raw])[-9:]
        vals = sorted(v for v in raw_log if v is not None)
        wait = None if raw is None or not vals else round(vals[len(vals) // 2] * k_day, 1)
        if state == "ok" and q_pub >= 1 and wait is not None:
            wait = max(wait, 0.3)                                              # 사람이 보이면 0분은 아니다(하한의 자리)
        measured = round(raw * k_day * r.gauss(1.0, 0.08), 1) if raw is not None and q_pub >= 3 else None
        recent_served.append((sec, served))
        recent_served = [(s, c) for s, c in recent_served if s > sec - 12 * 60]
        pts = None
        if with_points:
            seated = min(SEATS, sum(c for _, c in recent_served))
            pts = _points(r, queue, seated)
        out.append({"sec": sec, "queue": q_pub, "rate": rate, "wait": wait, "state": state, "raw": raw, "measured": measured,
                    "k": k_day if q_pub >= 3 else None, "served_n": served, "pts": pts})
    return out


def iso(date, sec):
    return f"{date.isoformat()}T{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def nutrients_for(date, kcal, ratio, std, salt="lunch"):
    """kcal·탄단지 비율 → NEIS 모양의 영양소 dict. 미량영양소는 권장량의 0.75~1.45 배(씨앗 난수) — 날마다 지표가 달라지되 그럴 법하게"""
    r = rng_for(date, f"nut{salt}")
    c, p, f = ratio
    n = {"carb_g": round(kcal * c / 4, 1), "protein_g": round(kcal * p / 4, 1), "fat_g": round(kcal * f / 9, 1)}
    for key, ref in std["per_meal"]["micro"].items():
        n[key] = round(ref["rni"] * r.uniform(0.75, 1.45), 1 if ref["rni"] > 5 else 2)
    return n


# ---------------- 생성 (설정·DB — main 이 환경을 정한 뒤에만 import) ----------------

def copy_templates(data):
    """git 템플릿 네 파일을 데모 폴더로 — 영양 기준·탄소 계수·구역 템플릿·피드 목록"""
    for name in ("nutrition_std.json", "carbon_std.json", "zones.json", "news_feeds.json"):
        shutil.copy(BASE / "data" / name, data / name)


def write_zones_local(data, anchor):
    """관리 앱 보정 탭이 '보정 끝난 상태' 로 보이게 — ROI·λ 변·보정 4점·호모그래피. 공개 화면은 쓰지 않는다"""
    from vision.zones import homography_from_4, load_zones, validate_zones
    img = [[0.08, 0.30], [0.92, 0.30], [0.98, 0.96], [0.02, 0.96]]
    floor = [[0.0, 0.60], [1.0, 0.60], [1.0, 0.0], [0.0, 0.0]]
    h = homography_from_4([tuple(p) for p in img], [tuple(p) for p in floor])
    doc = {"updated_at": anchor.replace(hour=11, minute=5, second=0).isoformat(timespec="seconds"), "updated_by": "demo",
           "camera": {"model": "imx708_wide", "fov_deg": 102, "note": "시연용 가상 보정 — 실제 급식실 값이 아니다"},
           "calib_points": [{"img": i, "floor": f} for i, f in zip(img, floor)], "image_to_floor": h,
           "roi": {"polygon": [[0.05, 0.42], [0.95, 0.42], [1.0, 1.0], [0.0, 1.0]], "lambda_edge": [0, 1], "out_dir": 1,
                   "lambda_inset": 0.05, "lambda_scale": 0.85}}
    (data / "zones.local.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    full = load_zones(data / "zones.json")
    errs = validate_zones(full)
    if errs:
        raise SystemExit(f"zones.local.json 검증 실패: {errs}")


def week_docs(days, anchor, std, carbon):
    """주별 meal.json 문서 — 집계(nutrition_days)는 전부, 화면은 기준일 주만 본다"""
    from jobs.fetch_neis import assess, carbon as carbon_of
    weeks = {}
    for d in days:
        weeks.setdefault(d - dt.timedelta(days=d.weekday()), []).append(d)
    docs = {}
    for monday, ds in sorted(weeks.items()):
        week = []
        for d in ds:
            mi = menu_index(d, anchor.date())
            menu, kcal, ratio, _ = MENUS[mi]
            kcal = round(kcal * rng_for(d, "kcal").uniform(0.97, 1.03), 1)
            n = nutrients_for(d, kcal, ratio, std)
            dmenu, dkcal, dratio = DINNERS[rng_for(d, "dinner").randrange(len(DINNERS))]
            dn = nutrients_for(d, dkcal, dratio, std, "dinner")
            week.append({"date": d.strftime("%Y%m%d"), "menu": menu, "kcal": kcal, "nutrients": n, "assess": assess(kcal, n), "carbon": carbon_of(kcal),
                         "dinner": {"menu": dmenu, "kcal": dkcal, "nutrients": dn, "assess": assess(dkcal, dn), "carbon": carbon_of(dkcal)}})

        def avg(key):
            vals = [x["assess"][key] for x in week if x["assess"][key] is not None]
            return round(sum(vals) / len(vals)) if vals else None
        today_s = anchor.strftime("%Y%m%d")
        docs[monday] = {"fetched_at": dt.datetime.combine(monday, dt.time(5, 40)).isoformat(timespec="seconds"), "result_code": "INFO-000", "state": "ok",
                        "std": {"school": std["school"], "group": std["group"], "source": std["source"]},
                        "today": next((x for x in week if x["date"] == today_s), None),
                        "week_avg": {"energy_pct": avg("energy_pct"), "mar": avg("mar")},
                        "carbon_std": {"ef_source": carbon["ef_source"], "capita_source": carbon["capita_source"]}, "week": week}
    return docs


def bulk_write(con, date, ticks, zones):
    """한 날의 틱들을 한 트랜잭션으로 — vision/record.write_sample 과 같은 표·열. 위치는 숫자(구역·타일 인원수)로만 남는다"""
    from vision.zones import count_by_cell, count_by_zone
    rows, zrows, crows = [], [], []
    for t in ticks:
        ts = iso(date, t["sec"])
        rows.append((ts, t["queue"], t["rate"], t["wait"], t["state"], t["raw"], t["measured"], t["k"], t["served_n"]))
        if t["pts"] is not None:
            zrows += [(ts, z, n) for z, n in count_by_zone(t["pts"], zones).items()]
            crows += [(ts, c, n) for c, n in count_by_cell(t["pts"]).items()]
    con.executemany("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.executemany("INSERT OR REPLACE INTO zone_samples VALUES (?,?,?)", zrows)
    con.executemany("INSERT OR REPLACE INTO cell_samples VALUES (?,?,?)", crows)
    con.commit()


def generate(data, anchor, log=print):
    """데모 폴더를 처음부터 만든다. 환경(DATA_DIR·DEMO_CLOCK…)이 정해진 뒤에 불러야 한다"""
    t0 = time.time()
    data.mkdir(parents=True, exist_ok=True)
    copy_templates(data)
    write_zones_local(data, anchor)
    std = json.loads((data / "nutrition_std.json").read_text(encoding="utf-8"))
    carbon = json.loads((data / "carbon_std.json").read_text(encoding="utf-8"))
    today = anchor.date()
    days = school_days(today)
    dayset = set(days)
    docs = week_docs(days, anchor, std, carbon)
    this_monday = today - dt.timedelta(days=today.weekday())
    (data / "meal.json").write_text(json.dumps(docs[this_monday], ensure_ascii=False, indent=1), encoding="utf-8")
    news = {"fetched_at": anchor.replace(hour=6, minute=12, second=0).isoformat(timespec="seconds"), "state": "ok", "translated": False, "engine": "sample", "model": None,
            "items": NEWS["climate"], "sections": [{"id": "climate", "label": "기후 · 환경", "items": NEWS["climate"]}, {"id": "tech", "label": "기술 · 과학 · IT", "items": NEWS["tech"]}],
            "keywords": KEYWORDS}
    (data / "news.json").write_text(json.dumps(news, ensure_ascii=False, indent=1), encoding="utf-8")

    from app.db import connect
    from vision.record import write_positions
    from vision.zones import load_zones
    zones = load_zones(data / "zones.json")["zones"]
    con = connect()
    anchor_sec = anchor.hour * 3600 + anchor.minute * 60 + anchor.second
    n_rows = 0
    for d in days:
        fine = (today - d).days < 7
        for lo, hi, n, mu, kind, f in waves_for(d, dayset, today):
            ticks = simulate_wave(d, lo, hi, n, mu, kind, f, today, tick=TICK if fine else COARSE_TICK, with_points=fine)
            if d == today:
                ticks = [t for t in ticks if t["sec"] < anchor_sec]            # 기준 시각 뒤는 피더가 '실시간' 으로 이어 쓴다
            if ticks:
                bulk_write(con, d, ticks, zones)
                n_rows += len(ticks)
                if d == today and ticks[-1]["pts"] is not None:
                    write_positions(iso(d, ticks[-1]["sec"]), len(ticks[-1]["pts"]), ticks[-1]["pts"])
    con.close()
    log(f"  queue.db  {len(days)}일 · 표본 {n_rows:,}행")

    # 집계 — jobs/rollup.py 의 함수 그대로(insights.db 의 writer 는 여전히 rollup 모듈)
    from app.config import DB_PATH, INSIGHTS_DB_PATH, REPORTS_DB_PATH
    from app.insight_calc import day_summary
    from app.insights_db import connect_ro
    from app.lunch import agg_meals
    from jobs import rollup
    qcon = connect_ro(DB_PATH, "samples")
    icon = sqlite3.connect(INSIGHTS_DB_PATH, timeout=5)
    icon.execute("PRAGMA journal_mode=WAL")
    rollup.migrate(icon)
    rollup.check_meta(icon, "lunch", "mock")
    for doc in docs.values():
        rollup.upsert_nutrition(icon, doc)
    icon.commit()
    n_days = 0
    for d in days:
        samples, zrows = rollup.read_day(qcon, d.isoformat())
        if not samples:
            continue
        for meal_name, lo, hi in agg_meals("lunch"):
            s = day_summary(samples, d.isoformat(), lo, hi, anchor_sec if d == today else None)
            if s["n_samples"]:
                rollup.write_day(icon, s, zrows, rollup.menu_for(icon, d.isoformat(), meal_name), "mock", meal_name)
        n_days += 1
    n_menus = rollup.rebuild_menu_stats(icon)
    yday = max(d for d in days if d < today)
    ran = dt.datetime.combine(yday, dt.time(14, 10, 4))
    icon.execute("INSERT INTO runs (started_at, finished_at, args, dates, n_days, ok) VALUES (?,?,?,?,?,1)",
                 (ran.isoformat(timespec="seconds"), (ran + dt.timedelta(seconds=7)).isoformat(timespec="seconds"), "--days 2", f"{yday},{today}", n_days))
    icon.commit()
    icon.close()
    qcon.close()
    log(f"  insights.db  {n_days}일 집계 · 메뉴 {n_menus}개")

    # 리포트 — jobs/report.py run 그대로(규칙 템플릿). 오늘은 아침 예보, 어제는 점심 결산
    from jobs import report
    res, _ = report.run("preview", today.isoformat(), meal=docs[this_monday], template_only=True, log=lambda *a: None)
    res2, _ = report.run("recap", yday.isoformat(), template_only=True, log=lambda *a: None)
    log(f"  reports.db  예보 「{res['headline'] if res else '-'}」 · 결산 「{res2['headline'] if res2 else '-'}」")
    log(f"  생성 {time.time() - t0:.1f}초 → {data}")
    return {"days": len(days), "rows": n_rows, "reports": REPORTS_DB_PATH.exists()}


# ---------------- 피더 · 서버 ----------------

def feeder(data, anchor, stop):
    """가상 시계가 가리키는 시각의 오늘 표본을 10초마다 이어 쓴다(카메라 노드의 대역). 창 밖에는 아무것도 쓰지 않는다 — 실제 vision 과 같다"""
    from app import clock
    from app.db import connect
    from vision.record import write_sample
    from vision.zones import load_zones
    today = anchor.date()
    days = set(school_days(today))
    zones = load_zones(data / "zones.json")["zones"]
    plan = {}
    for lo, hi, n, mu, kind, f in waves_for(today, days, today):
        for t in simulate_wave(today, lo, hi, n, mu, kind, f, today):
            plan[t["sec"]] = t
    anchor_sec = anchor.hour * 3600 + anchor.minute * 60 + anchor.second
    written = anchor_sec - TICK
    con = connect()
    while not stop.is_set():
        now = clock.now()
        sec = now.hour * 3600 + now.minute * 60 + now.second
        if now.date() != today:                                               # 자정을 넘기면(가상) 멈춘다 — 다음 날 표본은 만들지 않는다
            break
        for s in range((written // TICK + 1) * TICK, sec + 1, TICK):
            t = plan.get(s)
            if t is not None:
                write_sample(con, iso(today, s), {"queue": t["queue"], "rate": t["rate"], "wait": t["wait"], "state": t["state"], "pts": t["pts"],
                                                  "raw": t["raw"], "measured": t["measured"], "k": t["k"], "served_n": t["served_n"]}, zones)
            written = s
        stop.wait(2.0)
    con.close()


def serve(data, anchor, port, admin_port, open_browser):
    import uvicorn
    from app.main import app
    stop = threading.Event()
    threading.Thread(target=feeder, args=(data, anchor, stop), daemon=True, name="demo-feeder").start()
    url = f"http://127.0.0.1:{port}/"
    admin_url = None
    if admin_port:
        from app.admin.server import app as admin_app
        cfg = uvicorn.Config(admin_app, host="127.0.0.1", port=admin_port, log_level="warning")
        threading.Thread(target=uvicorn.Server(cfg).run, daemon=True, name="demo-admin").start()
        admin_url = f"http://127.0.0.1:{admin_port}/?key={os.environ['ADMIN_LOCAL_KEY']}"
    print("\n" + "=" * 72)
    print(f"  Mealboard 시연 모드 — 공개 화면  {url}   (가상 시계 {anchor:%Y-%m-%d %a %H:%M} 부터)")
    if admin_url:
        print(f"  관리 앱(보정 편집기·시스템)      {admin_url}")
    print("  화면 아래(또는 왼쪽) '앱 안내' 탭 → '자동 시연 시작' 을 누르면 여섯 화면을 돌며 설명합니다. 끝내려면 Ctrl+C")
    print("=" * 72 + "\n")
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url + "#wait")).start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    finally:
        stop.set()


def main(argv=None):
    ap = argparse.ArgumentParser(description="심사위원 구동 경로 — 모의 데이터 + 가상 시계로 전체 화면을 한 줄로")
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--data", default="data/demo", help="데모 데이터 폴더(운영 data/ 와 분리)")
    ap.add_argument("--anchor", default=ANCHOR, help="가상 시계 기준 시각 YYYY-MM-DDTHH:MM:SS")
    ap.add_argument("--keep", action="store_true", help="기존 데모 데이터를 지우지 않고 그대로 쓴다(기본은 매번 새로 만든다 — 결정론적이라 같은 결과)")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--with-admin", action="store_true", help="관리 앱도 함께(포트 +1)")
    ap.add_argument("--generate-only", action="store_true", help="데이터만 만들고 서버는 띄우지 않는다")
    a = ap.parse_args(argv)

    anchor = dt.datetime.fromisoformat(a.anchor)
    data = (BASE / a.data).resolve() if not Path(a.data).is_absolute() else Path(a.data)
    if data == (BASE / "data").resolve():
        raise SystemExit("데모 폴더는 운영 data/ 와 같을 수 없다 — --data data/demo 처럼 다른 폴더를 준다")
    # 환경은 app.config 를 읽기 전에 — .env 값보다 우선한다(load_dotenv 는 이미 있는 변수를 덮지 않는다)
    os.environ.update({"DATA_DIR": str(data), "DEMO_CLOCK": anchor.isoformat(timespec="seconds"), "SHOW_GUIDE": "1",
                       "FEED_SOURCE": "mock", "ROLLUP_WINDOW": "lunch", "API_PORT": str(a.port), "WAIT_FLOOR_MIN": "0",
                       "RUN_DIR": str(data / "run"), "LLM_HEF": "", "LLM_REPORT": "0",
                       "MEAL_WINDOWS": "11:20-12:30 3학년 점심;12:30-13:40 1·2학년 점심;17:30-18:30 석식",
                       "MEAL_WINDOWS_EVE": "11:20-12:30 3학년 점심;12:30-13:40 1·2학년 점심;17:00-18:00 석식",
                       "LUNCH_START": "11:30", "LUNCH_END": "13:40", "DINNER_START": "17:00", "DINNER_END": "18:30"})
    if a.with_admin:
        os.environ.update({"ADMIN_PORT": str(a.port + 1), "ADMIN_LOCAL_KEY": secrets.token_hex(8), "ADMIN_USERS": "", "CF_ACCESS_TEAM": "", "CF_ACCESS_AUD": ""})

    fresh = not (a.keep and (data / "queue.db").exists())
    if fresh:
        if data.exists():
            shutil.rmtree(data)                                                # 데모 폴더만 — 운영 data/ 는 위에서 막았다
        print(f"모의 데이터 생성 중 — 기준 {anchor:%Y-%m-%d %H:%M}, {WEEKS}주치")
        generate(data, anchor)
    else:
        print(f"기존 데모 데이터 사용 — {data}")
    if a.generate_only:
        return 0
    serve(data, anchor, a.port, a.port + 1 if a.with_admin else None, not a.no_browser)
    return 0


if __name__ == "__main__":
    sys.exit(main())
