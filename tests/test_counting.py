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
