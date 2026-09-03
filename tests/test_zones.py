"""구역 정의·판정·호모그래피. 저장소의 data/zones.json 템플릿이 그대로 통과해야 한다."""
import copy
import json
import math
from pathlib import Path

import pytest

from vision.zones import (count_by_zone, homography_from_4, invert, is_simple, load_zones, point_in_polygon,
                          polygon_area_m2, project, validate_zones, zone_of)

TEMPLATE = Path(__file__).resolve().parents[1] / "data" / "zones.json"
SQUARE = [[0, 0], [1, 0], [1, 1], [0, 1]]


@pytest.fixture
def doc():
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def test_저장소_템플릿은_검증을_통과한다(doc):
    assert validate_zones(doc) == []
    assert [z["id"] for z in doc["zones"]] == ["counter", "aisle", "seating"]


def test_점_판정_경계는_아래_왼쪽만_안():
    assert point_in_polygon(0.5, 0.5, SQUARE)
    assert point_in_polygon(0.0, 0.0, SQUARE)
    assert not point_in_polygon(1.0, 0.5, SQUARE)
    assert not point_in_polygon(0.5, 1.0, SQUARE)
    assert not point_in_polygon(1.2, 0.5, SQUARE)


def test_구역은_첫_일치_우선이고_맞닿은_경계는_한_번만(doc):
    zones = doc["zones"]
    assert zone_of(0.5, 0.05, zones) == "counter"
    assert zone_of(0.05, 0.5, zones) == "aisle"
    assert zone_of(0.5, 0.5, zones) == "seating"
    assert zone_of(0.05, 0.10, zones) == "aisle"          # y=0.10 경계: 배식대(위 경계=밖) 가 아니라 통로
    assert zone_of(0.1415, 0.5, zones) == "seating"       # x=0.1415 경계: 통로(오른 경계=밖) 가 아니라 좌석
    assert zone_of(0.5, 1.0, zones) is None               # 출입문 벽 위의 점은 어느 구역도 아니다


def test_구역별_인원수는_모든_구역을_0_포함으로(doc):
    pts = [{"x": 0.5, "y": 0.05}, {"x": 0.6, "y": 0.02}, (0.05, 0.5), (0.5, 1.0)]
    assert count_by_zone(pts, doc["zones"]) == {"counter": 2, "aisle": 1, "seating": 0}
    assert count_by_zone([], doc["zones"]) == {"counter": 0, "aisle": 0, "seating": 0}


def test_실제_면적은_폭_곱하기_길이(doc):
    counter = doc["zones"][0]["polygon"]
    assert polygon_area_m2(counter, doc["floor"]) == pytest.approx(15.55 * 24.65 * 0.10)
    assert polygon_area_m2(SQUARE, doc["floor"]) == pytest.approx(15.55 * 24.65)


def test_나비넥타이는_단순_다각형이_아니다():
    assert is_simple(SQUARE)
    assert not is_simple([[0, 0], [1, 1], [1, 0], [0, 1]])


@pytest.mark.parametrize("mutate, keyword", [
    (lambda d: d.update(version=2), "version"),
    (lambda d: d.update(extra=1), "미지 키"),
    (lambda d: d["zones"][0].update(id="Counter"), "id"),
    (lambda d: d["zones"][1].update(id="counter"), "중복"),
    (lambda d: d["zones"][0].update(polygon=[[0, 0], [1, 0]]), "3개"),
    (lambda d: d["zones"][0].update(polygon=[[0, 0], [1.2, 0], [1, 1]]), "0~1"),
    (lambda d: d["zones"][0].update(polygon=[[0, 0], [1, 1], [1, 0], [0, 1]]), "교차"),
    (lambda d: d["zones"][0].update(polygon=[[0, 0], [0.001, 0], [0, 0.001]]), "면적"),
    (lambda d: d.update(zones=[]), "zones"),
    (lambda d: d["floor"].update(width_m=0), "floor"),
    (lambda d: d.update(buffer_px=-1), "buffer_px"),
    (lambda d: d.update(roi={"polygon": SQUARE, "lambda_edge": [0, 2], "out_dir": 1}), "lambda_edge"),
    (lambda d: d.update(roi={"polygon": SQUARE, "lambda_edge": [0, 1], "out_dir": 0}), "out_dir"),
    (lambda d: d.update(image_to_floor=[[1, 0, 0], [0, 1, 0], [0, 0, 0]]), "특이"),
    (lambda d: d.update(image_to_floor=[[1, 0], [0, 1]]), "3×3"),
    (lambda d: d.update(calib_points=[{"img": [0, 0], "floor": [0, 0]}]), "calib_points"),
])
def test_규칙_위반은_문장으로_보고한다(doc, mutate, keyword):
    d = copy.deepcopy(doc)
    mutate(d)
    errors = validate_zones(d)
    assert errors and any(keyword in msg for msg in errors), errors


def test_roi_정상_형태와_마지막_변의_인접(doc):
    doc["roi"] = {"polygon": SQUARE, "lambda_edge": [3, 0], "out_dir": -1}
    assert validate_zones(doc) == []


def test_호모그래피_왕복():
    img = [[0.1, 0.9], [0.9, 0.9], [0.7, 0.2], [0.3, 0.2]]      # 카메라에 잡힌 사다리꼴
    floor = [[0, 0], [1, 0], [1, 1], [0, 1]]                    # 바닥의 직사각형
    h = homography_from_4(img, floor)
    for (u, v), (x, y) in zip(img, floor):
        assert math.dist(project(h, u, v), (x, y)) < 1e-9
    hi = invert(h)
    assert math.dist(project(hi, *project(h, 0.5, 0.5)), (0.5, 0.5)) < 1e-9


def test_퇴화한_대응점은_예외():
    with pytest.raises(ValueError):
        homography_from_4([[0, 0], [0.5, 0.5], [1, 1], [0.2, 0.2]], SQUARE)


def test_재투영_오차가_크면_거부(doc):
    img = [[0.1, 0.9], [0.9, 0.9], [0.7, 0.2], [0.3, 0.2]]
    h = homography_from_4(img, SQUARE)
    doc["calib_points"] = [{"img": list(p), "floor": list(q)} for p, q in zip(img, SQUARE)]
    doc["image_to_floor"] = h
    assert validate_zones(doc) == []
    doc["calib_points"][0]["floor"] = [0.05, 0.05]
    assert any("재투영" in m for m in validate_zones(doc))


def test_로컬_파일이_템플릿을_덮어쓴다(tmp_path, doc):
    (tmp_path / "zones.json").write_text(json.dumps(doc), encoding="utf-8")
    assert load_zones(tmp_path / "zones.json")["roi"] is None
    (tmp_path / "zones.local.json").write_text(
        json.dumps({"roi": {"polygon": SQUARE, "lambda_edge": [0, 1], "out_dir": 1}, "updated_by": "admin"}), encoding="utf-8")
    merged = load_zones(tmp_path / "zones.json")
    assert merged["roi"]["lambda_edge"] == [0, 1] and merged["updated_by"] == "admin"
    assert [z["id"] for z in merged["zones"]] == ["counter", "aisle", "seating"]   # 덮어쓰지 않은 키는 그대로


@pytest.mark.parametrize("local", ['{"zones": []}', "null", "[1, 2]", "{broken"])
def test_깨진_로컬_파일은_언제나_ValueError(tmp_path, doc, local):
    (tmp_path / "zones.json").write_text(json.dumps(doc), encoding="utf-8")
    (tmp_path / "zones.local.json").write_text(local, encoding="utf-8")
    with pytest.raises(ValueError):
        load_zones(tmp_path / "zones.json")


def test_템플릿이_객체가_아니어도_ValueError(tmp_path):
    (tmp_path / "zones.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_zones(tmp_path / "zones.json")


def test_육각_타일_번호와_셀별_인원수():
    from vision.zones import GRID_COLS, GRID_ROWS, cell_of, count_by_cell, hex_center
    assert cell_of(0, 0) == 0 and cell_of(1, 1) == GRID_COLS * GRID_ROWS - 1 and cell_of(0.99, 0) == GRID_COLS - 1
    assert all(cell_of(*hex_center(c)) == c for c in range(GRID_COLS * GRID_ROWS))     # 타일 중심은 자기 타일로
    assert cell_of(0.5, 0.5, 4, 4) == 1 * 4 + 1                                          # 홀수 행은 반 칸 오른쪽 — 정사각 격자(2,2)와 다르다
    cx, cy = hex_center(GRID_COLS + 1)                                                   # 행 1 열 1 의 중심은 행 0 열 1 보다 반 칸 오른쪽
    assert abs(cx - (hex_center(1)[0] + 0.5 / GRID_COLS)) < 1e-9 and cy > hex_center(1)[1]
    c = count_by_cell([{"x": 0.03, "y": 0.02}, {"x": 0.05, "y": 0.03}, (0.9, 0.9)])   # 타일이 작아져 첫 두 점은 같은 타일 안에서 골랐다
    assert c == {0: 2, cell_of(0.9, 0.9): 1} and sum(c.values()) == 3
