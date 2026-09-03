"""구역 편집기 저장소(PLAN §4.3 zones) — local 만 쓰고 템플릿은 그대로, 백업 5개 회전, 검증 거부, 호모그래피."""
import datetime as dt
import json
import pathlib

import pytest

from app.admin import zones_store
from vision.zones import REPROJ_TOL

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def env(tmp_path):
    tpl = tmp_path / "zones.json"
    tpl.write_text((ROOT / "data" / "zones.json").read_text(encoding="utf-8"), encoding="utf-8")
    return tpl, tmp_path / "zones.local.json"


def test_읽기는_템플릿에_로컬을_덮어쓴_결과(env):
    tpl, local = env
    r = zones_store.read(tpl, local)
    assert r["local"] is False and r["doc"]["version"] == 1 and r["backups"] == []
    local.write_text(json.dumps({"buffer_px": 33}), encoding="utf-8")
    assert zones_store.read(tpl, local)["doc"]["buffer_px"] == 33 and zones_store.read(tpl, local)["local"]


def test_쓰기는_로컬만_바꾸고_템플릿은_그대로(env):
    tpl, local = env
    before = tpl.read_text(encoding="utf-8")
    doc = zones_store.read(tpl, local)["doc"]
    doc["buffer_px"] = 25
    saved, bak = zones_store.write(doc, "t@example.com", template=tpl, local=local, now=dt.datetime(2026, 9, 3, 12, 0, 0))
    assert bak is None and local.is_file() and tpl.read_text(encoding="utf-8") == before
    assert saved["updated_by"] == "t@example.com" and saved["updated_at"] == "2026-09-03T12:00:00"
    over = json.loads(local.read_text(encoding="utf-8"))
    assert over["buffer_px"] == 25 and set(over) == {"buffer_px", "updated_at", "updated_by"}     # 바뀐 키만 — 나머지는 템플릿을 계속 따른다
    assert zones_store.read(tpl, local)["doc"]["buffer_px"] == 25            # GET 왕복
    # 템플릿이 나중에 바뀌면(git pull) 손대지 않은 키는 그것을 따른다; version 은 언제나 템플릿의 것
    t2 = json.loads(before); t2["note"] = "새 메모"; t2["version"] = 1
    tpl.write_text(json.dumps(t2, ensure_ascii=False), encoding="utf-8")
    assert zones_store.read(tpl, local)["doc"]["note"] == "새 메모"
    zones_store.write({**doc, "version": 99}, "t", template=tpl, local=local)
    assert "version" not in json.loads(local.read_text(encoding="utf-8"))


def test_백업은_최신_5개만(env):
    tpl, local = env
    doc = zones_store.read(tpl, local)["doc"]
    for i in range(8):
        doc["buffer_px"] = i
        _, bak = zones_store.write(doc, "t", template=tpl, local=local, now=dt.datetime(2026, 9, 3, 12, 0, i))
        assert (bak is None) == (i == 0)
    baks = zones_store.backups(local)
    assert len(baks) == zones_store.KEEP_BAK == 5 and baks[0].endswith("120007") and baks[-1].endswith("120003")
    assert json.loads(local.with_name(baks[0]).read_text(encoding="utf-8"))["buffer_px"] == 6   # 직전 판


def test_검증_실패는_아무것도_쓰지_않는다(env):
    tpl, local = env
    doc = zones_store.read(tpl, local)["doc"]
    doc["roi"] = {"polygon": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]], "lambda_edge": [0, 2], "out_dir": 1}
    with pytest.raises(zones_store.Invalid) as ei:
        zones_store.write(doc, "t", template=tpl, local=local)
    assert any("lambda_edge" in m for m in ei.value.errors) and not local.exists()
    with pytest.raises(zones_store.Invalid):
        zones_store.write(["not", "a", "doc"], "t", template=tpl, local=local)
    with pytest.raises(zones_store.Invalid):
        zones_store.write({**doc, "roi": None, "zones": []}, "t", template=tpl, local=local)


def test_호모그래피_왕복과_거부():
    pairs = [{"img": [0.1, 0.9], "floor": [0.0, 0.0]}, {"img": [0.9, 0.9], "floor": [1.0, 0.0]},
             {"img": [0.7, 0.2], "floor": [1.0, 1.0]}, {"img": [0.3, 0.2], "floor": [0.0, 1.0]}]
    r = zones_store.homography(pairs)
    assert r["ok"] and r["reproj_err"] < REPROJ_TOL and len(r["image_to_floor"]) == 3 and len(r["floor_to_image"]) == 3
    with pytest.raises(zones_store.Invalid):
        zones_store.homography(pairs[:3])
    with pytest.raises(zones_store.Invalid):
        zones_store.homography([{"img": [0, 0], "floor": [0, 0]}] * 4)          # 퇴화
    with pytest.raises(zones_store.Invalid):
        zones_store.homography([{"img": [0, 2], "floor": [0, 0]}] + pairs[1:])    # 범위 밖
