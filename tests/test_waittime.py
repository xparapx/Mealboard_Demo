from vision.waittime import estimate_wait


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
