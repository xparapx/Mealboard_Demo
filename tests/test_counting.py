"""라인크로싱·처리율(vision/counting.py) — 카메라 없이 도는 순수 로직만 본다."""
from vision.counting import LineCounter, RateWindow, cross, foot_of_bbox, signed_dist


def test_기준점은_바닥_중앙():
    assert foot_of_bbox(10, 20, 30, 60) == (20, 60)


def test_외적_부호는_편집기와_같다():
    a, b = (0, 0), (100, 0)
    assert cross(a, b, (50, 10)) > 0          # i→j 의 왼쪽(이미지 y 아래) = out_dir 1 의 출구 쪽
    assert cross(a, b, (50, -10)) < 0
    assert signed_dist(a, b, (50, 30)) == 30


def test_완충띠_안에서는_판정을_미룬다():
    c = LineCounter((0, 0), (100, 0), out_dir=1, buffer=20)
    assert c.update(7, (50, -30)) == 0        # 첫 관측 — 안쪽에 있다고 기억만
    assert c.update(7, (50, 10)) == 0         # 띠 안 — 아직
    assert c.update(7, (50, -5)) == 0         # 띠 안에서 되돌아가도 아무 일 없음
    assert c.update(7, (50, 30)) == 1         # 출구 쪽으로 확정 → 1명 통과
    assert c.update(7, (50, 40)) == 0         # 같은 쪽에 머묾
    assert c.update(7, (50, -30)) == -1       # 다시 안쪽으로 → 되돌아옴


def test_out_dir_뒤집기():
    c = LineCounter((0, 0), (100, 0), out_dir=-1, buffer=5)
    c.update(1, (50, 30))
    assert c.update(1, (50, -30)) == 1        # -1 이면 오른쪽(y 위)이 출구


def test_트랙별_독립_기억과_forget():
    c = LineCounter((0, 0), (100, 0), out_dir=1, buffer=5)
    c.update(1, (10, -30)); c.update(2, (10, 30))
    assert c.update(1, (10, 30)) == 1 and c.update(2, (10, -30)) == -1
    c.forget([2])
    assert set(c.side) == {2}
    c.reset()
    assert c.side == {}


def test_처리율은_5분_이동합():
    r = RateWindow(300)
    for t in range(0, 300, 10):
        r.add(t, 1)                            # 30명이 5분에
    assert r.per_min(299) == 6.0
    assert r.per_min(600) == 0.0              # 창을 벗어나면 빠진다
    r.add(600, 0)
    assert r.per_min(600) == 0.0 and not r.events


# ---- 자동 실측·보정 (09-16 B안) --------------------------------------------------------------

def test_dwell_진입에서_통과까지_체류를_잰다():
    from vision.counting import DwellTracker
    d = DwellTracker()
    d.observe(1, True, 100.0, 2.0)                 # 진입(그때 예측 2.0분)
    d.observe(1, True, 110.0, 2.5)                 # 이미 기억 — 리셋하지 않는다
    assert d.crossed(1, 220.0) == 120.0            # 2분 체류
    assert d.crossed(1, 230.0) is None             # 두 번 통과해도 진입 기록은 한 번뿐


def test_dwell_짧은_체류와_진입_기록_없는_통과는_버린다():
    from vision.counting import DwellTracker
    d = DwellTracker()
    d.observe(1, True, 100.0, 2.0)
    assert d.crossed(1, 110.0) is None             # 20초 미만 — 트랙 재부여·선 근처 출생
    assert d.crossed(9, 200.0) is None             # 진입을 본 적 없는 트랙
    assert d.stats(200.0) == {"n": 0, "measured_min": None, "k": None}


def test_dwell_보정계수는_비율_중앙값을_클램프():
    from vision.counting import DwellTracker
    d = DwellTracker()
    for i in range(5):                             # 예측 1분인데 실제 2분 — 비율 2.0 이 다섯 번
        d.observe(i, True, 100.0 + i, 1.0)
        d.crossed(i, 220.0 + i)
    s = d.stats(230.0)
    assert s["n"] == 5 and s["measured_min"] == 2.0 and s["k"] == 2.0
    d2 = DwellTracker()
    for i in range(5):                             # 비율 6.0 → 상한 3.0 으로 눌린다
        d2.observe(i, True, 100.0, 0.5)
        d2.crossed(i, 280.0)
    assert d2.stats(300.0)["k"] == DwellTracker.CLAMP[1]


def test_dwell_예측이_너무_작으면_비율에서_뺀다():
    from vision.counting import DwellTracker
    d = DwellTracker()
    for i in range(5):
        d.observe(i, True, 100.0, 0.1)             # 진입 예측 0.1분 < MIN_PRED — 비율 폭주 방지
        d.crossed(i, 200.0)
    s = d.stats(210.0)
    assert s["n"] == 5 and s["measured_min"] is not None and s["k"] is None


def test_dwell_이동_창_밖_이벤트는_빠진다():
    from vision.counting import DwellTracker
    d = DwellTracker(window_sec=100)
    d.observe(1, True, 0.0, 1.0)
    d.crossed(1, 60.0)
    assert d.stats(60.0)["n"] == 1
    assert d.stats(200.0)["n"] == 0


def test_중앙값_창은_None을_거르고_만료시킨다():
    from vision.counting import MedianWindow
    m = MedianWindow(window_sec=25)
    for i, v in enumerate([3, 0, 3, None, 4]):     # 검출 깜빡임(0)·결측(None)이 섞여도
        m.add(float(i), v)
    assert m.median(4.0) == 3                       # 중앙값은 추세(3)를 지킨다
    assert m.median(100.0) is None                  # 창을 지나면 비워진다


def test_중앙값_짝수개는_가운데_평균():
    from vision.counting import MedianWindow
    m = MedianWindow(window_sec=90)
    for i, v in enumerate([2.0, 4.0, 6.0, 8.0]):
        m.add(float(i), v)
    assert m.median(3.0) == 5.0
    m.reset()
    assert m.median(3.0) is None
