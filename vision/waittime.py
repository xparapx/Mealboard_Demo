"""대기시간 추정 — Little's law  W = L / λ
순수 함수만 둔다. 카메라·DB 를 모르므로 PC 에서도 그대로 테스트된다."""

MIN_RATE = 0.5   # 명/분. 이보다 낮으면 나눗셈이 폭주하므로 '산출 불가'로 처리


def estimate_wait(queue_len, rate_per_min):
    """(예상 대기 분, 상태) 를 돌려준다.
    상태: ok | no_data | insufficient_rate
    """
    if queue_len is None or rate_per_min is None:
        return None, "no_data"
    if queue_len <= 0:
        return 0.0, "ok"
    if rate_per_min < MIN_RATE:
        return None, "insufficient_rate"
    return round(queue_len / rate_per_min, 1), "ok"


def apply_floor(wait, queue_len, measured_min=None, floor_min=0.0):
    """공표 하한(09-17 자동 체류 중앙값 + 10-15 수동 실측 하한). 줄에 사람이 보이는데(L≥1) 공표가 하한보다 낮으면 하한으로 올린다.
    하한 = max(자동 실측 중앙값, .env WAIT_FLOOR_MIN). 수동 하한은 ROI 가 줄의 일부만 덮어 L 이 포화될 때(10-15: 수동 1.5분 vs 공표 0.3분,
    λ 15/분이면 실제 줄 ≈24명 vs L 4) 자동 실측도 못 살리는 꼬리를 메우는 임시 처방 — 근본 대책은 화각·ROI 가 줄 전체를 덮는 것.
    wait 가 None(산출 불가)이거나 L=0 이면 손대지 않는다"""
    if wait is None or queue_len is None or queue_len < 1:
        return wait
    floor = max(float(measured_min or 0.0), float(floor_min or 0.0))
    return round(floor, 1) if floor > wait else wait
