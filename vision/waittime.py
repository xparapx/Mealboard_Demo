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
