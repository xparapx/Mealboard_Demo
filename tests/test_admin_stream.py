"""스트림(PLAN §4.4) — 플래그 파일 규칙, 허브의 drop-oldest·bind/unbind, 프록시 머리 파싱, mock 프레임 스키마. 네트워크 없이 돈다."""
import asyncio
import datetime as dt
import json

import pytest

from app.admin import stream
from app.admin.stream import MetaHub, StreamState, clamp_minutes, flag_read, flag_write, parse_head, remaining_s
from jobs.mock_feed import frame_event, to_image
from vision.meta import MAX_BYTES, MetaSender, encode


def test_분은_1_10_으로_눌린다():
    assert clamp_minutes(2) == 2 and clamp_minutes(0) == 1 and clamp_minutes(99) == 10
    assert clamp_minutes("x") == stream.DEFAULT_MIN and clamp_minutes(None) == stream.DEFAULT_MIN


def test_플래그_읽기_쓰기_남은_시간(tmp_path):
    f = tmp_path / "debug_on"
    assert flag_read(f) is None and remaining_s(None) == 0
    until = dt.datetime(2026, 9, 3, 12, 0, 0)
    flag_write(f, until, "t@example.com", 2)
    d = flag_read(f)
    assert d["until"] == until and d["by"] == "t@example.com" and d["minutes"] == 2
    assert remaining_s(d, dt.datetime(2026, 9, 3, 11, 59, 30)) == 30
    assert remaining_s(d, dt.datetime(2026, 9, 3, 12, 0, 1)) == 0


def test_깨진_플래그는_mtime_10분_규칙으로_본다(tmp_path):
    f = tmp_path / "debug_on"
    f.write_text("not json")
    d = flag_read(f)
    assert d["by"] is None and 0 < remaining_s(d) <= stream.MAX_MIN * 60
    flag_write(f, dt.datetime.now() + dt.timedelta(hours=5), None, 300)     # 손으로 늘린 until 도 mtime+10분을 넘지 못한다
    assert remaining_s(flag_read(f)) <= stream.MAX_MIN * 60


def test_뷰어_자리는_동기적으로_하나만(tmp_path):
    st = StreamState(flag=tmp_path / "debug_on", port=1, hub=MetaHub(run_dir=tmp_path, port=18107))
    assert st.claim() and not st.claim() and st.viewers == 1
    st.release(); st.release()
    assert st.viewers == 0 and st.claim()


def test_스트림_라우트는_전부_async(tmp_path):
    """루프 타이머(call_later)·Event 를 잡는 엔드포인트가 동기 def 로 돌아가면(스레드풀) 500 — 회귀 방지"""
    import inspect
    from app.admin.routers import stream as r
    assert all(inspect.iscoroutinefunction(route.endpoint) for route in r.router.routes)


def test_off_는_릴레이에_바로_전해진다(tmp_path, monkeypatch):
    monkeypatch.setattr(stream.audit, "log", lambda *a, **k: None)

    async def go():
        st = StreamState(flag=tmp_path / "debug_on", port=1, hub=MetaHub(run_dir=tmp_path, port=18108))
        st.turn_on(1, None)
        assert not st.off.is_set()

        class Stall:                                   # 열려 있지만 아무것도 보내지 않는 upstream
            async def read(self, n): await asyncio.sleep(3600)

        class W:
            def close(self): pass
        st.claim()
        gen = st.relay(Stall(), W(), None)
        task = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0.2)
        st.turn_off(None)                              # off → 1초 안에 릴레이 종료, 자리 반납
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(task, 3)
        assert st.viewers == 0 and st.off.is_set()
    asyncio.run(go())


def test_응답_머리_파싱():
    head = b"HTTP/1.0 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=frame\r\nCache-Control: no-cache\r\n\r\n"
    status, h = parse_head(head)
    assert status == 200 and h["content-type"].startswith("multipart/x-mixed-replace")
    assert parse_head(b"garbage\r\n\r\n")[0] == 0


def test_허브_drop_oldest_와_구독_상한():
    hub = MetaHub()
    q = asyncio.Queue(stream.QUEUE_N)
    hub.subs.add(q)
    for i in range(stream.QUEUE_N + 3):
        hub.datagram_received(str(i).encode(), None)
    got = [q.get_nowait() for _ in range(q.qsize())]
    assert got == [b"3", b"4", b"5", b"6", b"7"] and hub.frames == 8       # 가장 오래된 0·1·2 가 버려진다

    async def too_many():
        hub.subs.clear()
        hub.transport = object()                                     # bind 를 흉내낸다 — 여기서는 소켓을 열지 않는다
        for _ in range(stream.MAX_SUBS):
            await hub.subscribe()
        with pytest.raises(stream.HubFull):
            await hub.subscribe()
        hub.transport = None
    asyncio.run(too_many())


def test_허브는_구독자가_있을_때만_소켓을_연다(tmp_path):
    """bind → 데이터그램 도착 → 마지막 구독자 unsubscribe → 소켓 닫힘(POSIX 는 파일도 사라진다)"""
    async def go():
        hub = MetaHub(run_dir=tmp_path, port=18103)
        q = await hub.subscribe()
        assert hub.transport is not None and hub.info()["bound"]
        sender = MetaSender(run_dir=tmp_path, port=18103)
        assert sender.send({"frame_id": 1, "tracks": []})
        data = await asyncio.wait_for(q.get(), 2)
        assert json.loads(data)["frame_id"] == 1
        sender.close()
        hub.unsubscribe(q)
        assert hub.transport is None and not hub.subs
        if hub.unix:
            assert not hub.path.exists()
    asyncio.run(go())


def test_켜고_끄기와_자동_off(tmp_path, monkeypatch):
    logged = []
    monkeypatch.setattr(stream.audit, "log", lambda *a, **k: logged.append(a[1]))

    async def go():
        st = StreamState(flag=tmp_path / "debug_on", port=1, hub=MetaHub(run_dir=tmp_path, port=18104))
        assert st.state()["state"] == "off"
        s = st.turn_on(99, {"user": "t@example.com", "via": "tailscale"})
        assert s["state"] == "on" and s["minutes"] == 10 and 590 < s["remaining_s"] <= 600 and st.timer is not None
        st.turn_off({"user": "t@example.com", "via": "tailscale"})
        assert st.state()["state"] == "off" and st.timer is None and not (tmp_path / "debug_on").exists()
        st.turn_on(1, None)
        st.timer.cancel(); st._auto_off()                              # 타이머가 울린 것과 같다
        assert st.state()["state"] == "off"
        assert logged == ["stream.on", "stream.off", "stream.on", "stream.autooff"]
    asyncio.run(go())


def test_재시작_때_만료된_플래그는_지우고_남은_것은_이어간다(tmp_path, monkeypatch):
    logged = []
    monkeypatch.setattr(stream.audit, "log", lambda *a, **k: logged.append(a[1]))
    f = tmp_path / "debug_on"

    async def go():
        flag_write(f, dt.datetime.now() - dt.timedelta(seconds=1), None, 1)
        st = StreamState(flag=f, port=1, hub=MetaHub(run_dir=tmp_path, port=18105))
        await st.resume()
        assert not f.exists() and logged == ["stream.autooff"]
        flag_write(f, dt.datetime.now() + dt.timedelta(minutes=3), None, 3)
        await st.resume()
        assert st.timer is not None and st.is_on()
        st.shutdown()
    asyncio.run(go())


def test_mjpeg_는_vision_없으면_OSError(tmp_path):
    async def go():
        st = StreamState(flag=tmp_path / "debug_on", port=1, hub=MetaHub(run_dir=tmp_path, port=18106))   # 포트 1 — 아무도 없다
        with pytest.raises((OSError, asyncio.TimeoutError)):
            await st.open_upstream()
    asyncio.run(go())


def test_mock_프레임은_스키마대로_정규화_좌표만():
    zones = [{"id": "counter", "polygon": [[0, 0], [1, 0], [1, 0.1], [0, 0.1]]}]
    pts = [{"x": 0.5, "y": 0.05}, {"x": 0.1, "y": 0.9}]
    ev = frame_event(7, "2026-09-03T12:00:00.000", pts, zones, 12.3456, 4, "ok", [{"id": 1000, "dir": "out", "ts": "t"}])
    assert set(ev) >= {"frame_id", "ts", "fps", "infer_ms", "img_w", "img_h", "tracks", "crossings", "zone_counts",
                       "roi_count", "rate_per_min", "wait_min", "state"}
    assert ev["frame_id"] == 7 and ev["roi_count"] == 1 and ev["rate_per_min"] == 12.35 and ev["zone_counts"] == {"counter": 1}
    t = ev["tracks"][0]
    assert t["in_roi"] and t["zone"] == "counter" and t["floor_xy_norm"] == [0.5, 0.05]
    for tr in ev["tracks"]:
        assert all(0 <= v <= 1 for v in tr["bbox_norm"] + tr["foot_xy_norm"] + tr["floor_xy_norm"])
        assert tr["bbox_norm"][0] <= tr["bbox_norm"][2] and tr["bbox_norm"][1] <= tr["bbox_norm"][3]
    assert to_image(0.5, 0)[1] > to_image(0.5, 1)[1]                    # 가까운 사람이 화면 아래


def test_너무_큰_프레임은_보내지_않는다():
    assert encode({"a": 1}) == b'{"a":1}'
    assert encode({"big": "x" * MAX_BYTES}) is None
