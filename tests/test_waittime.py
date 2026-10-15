from vision.waittime import apply_floor, estimate_wait


def test_basic():
    # 30명 대기, 분당 10명 처리 → 3분
    assert estimate_wait(30, 10) == (3.0, "ok")


def test_empty_queue():
    assert estimate_wait(0, 0) == (0.0, "ok")


def test_rate_too_low():
    # 배식이 아직 시작 안 됨 → 숫자를 내지 않는다
    assert estimate_wait(30, 0.1) == (None, "insufficient_rate")


def test_no_data():
    assert estimate_wait(None, 5) == (None, "no_data")


def test_apply_floor_수동_실측_하한():
    """10-15: ROI 포화로 공표 0.3분인데 수동 실측 중앙값 1.5분 — 줄이 보이면 하한으로 올린다"""
    assert apply_floor(0.3, 4, 0.3, 1.5) == 1.5
    assert apply_floor(0.3, 4, 0.9, 0.0) == 0.9          # 자동 실측 중앙값만 있을 때(09-17)
    assert apply_floor(2.0, 4, 0.9, 1.5) == 2.0          # 이미 하한 위면 그대로
    assert apply_floor(0.3, 0, 0.9, 1.5) == 0.3          # L=0 이면 손대지 않는다(줄이 없으면 하한도 없다)
    assert apply_floor(None, 4, 0.9, 1.5) is None        # 산출 불가는 그대로
    assert apply_floor(0.3, 4, None, 0) == 0.3
