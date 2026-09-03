"""규칙 템플릿 — LLM 이 없거나 출력이 검증에 떨어졌을 때의 리포트 문장 (PLAN §5.3). 순수 함수, 입력은 report.py 가 만든 dict.
출력 스키마는 LLM 경로와 같다: {headline ≤40, body ≤120, tone calm|busy|info}. 숫자는 입력에 있는 것만 쓴다(검증기와 같은 규칙)."""

WD = ["일", "월", "화", "수", "목", "금", "토"]        # SQLite %w 규칙(0=일요일)


def clip(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def hm(minute):
    return f"{int(minute) // 60}:{int(minute) % 60:02d}"


def menu_phrase(menu, k=2):
    m = [x for x in (menu or []) if x][:k]
    return "·".join(m) if m else "오늘 식단"


def preview(inp):
    """아침 예보 — 오늘 메뉴·요일·평소 곡선(같은 요일) → 언제 붐비는지"""
    wd = WD[inp.get("weekday", 0)] if isinstance(inp.get("weekday"), int) else ""
    menu = menu_phrase(inp.get("menu"))
    t = inp.get("typical") or {}
    if t.get("peak_minute") is not None and t.get("peak_wait") is not None:
        peak, wait = hm(t["peak_minute"]), t["peak_wait"]
        tone = "busy" if wait >= 8 else "calm"
        headline = clip(f"{wd}요일 {menu}, 평소 {peak} 전후가 가장 붐빕니다", 40)
        low = t.get("low_minute")
        body = clip(f"같은 요일 {t.get('days', 0)}일 기준 {peak}쯤 대기 {wait}분까지 올라갔습니다."
                    + (f" {hm(low)} 무렵은 한산했습니다." if low is not None else "")
                    + " 줄이 길면 잠시 뒤에 오세요.", 120)
    else:
        tone = "info"
        headline = clip(f"{wd}요일 급식은 {menu}", 40)
        body = clip("아직 이 요일의 평소 곡선이 없습니다. 대기시간 화면의 실시간 값을 보고 오세요.", 120)
    return {"headline": headline, "body": body, "tone": tone}


def recap(inp):
    """점심 결산 — 그날 집계 행(lunch_days)·이벤트 → 한 줄 요약"""
    menu = menu_phrase(inp.get("menu"))
    pw, pq = inp.get("peak_wait"), inp.get("peak_queue")
    pt = inp.get("peak_wait_hm")
    if pw is None:
        return {"headline": clip(f"{menu}, 오늘은 측정값이 부족했습니다", 40),
                "body": clip(f"표본 {inp.get('n_samples') or 0}개, 커버리지 {inp.get('coverage_pct') or 0}%. 카메라·카운팅 상태를 확인해 주세요.", 120),
                "tone": "info"}
    tone = "busy" if pw >= 8 else "calm"
    headline = clip(f"{menu}, 최대 대기 {pw}분" + (f" ({pt})" if pt else ""), 40)
    parts = [f"오늘 {inp.get('served_est') or 0}명이 배식대를 지났고 평균 대기 {inp.get('avg_wait') or 0}분이었습니다."]
    if pq is not None:
        parts.append(f"줄이 가장 길 때 {pq}명.")
    if inp.get("golden_min"):
        parts.append(f"여유 구간 {inp['golden_min']}분.")
    if inp.get("bottleneck_min"):
        parts.append(f"병목 {inp['bottleneck_min']}분.")
    return {"headline": headline, "body": clip(" ".join(parts), 120), "tone": tone}


def render(kind, inp):
    return preview(inp) if kind == "preview" else recap(inp)
