"""구역·ROI·호모그래피 — 순수 함수. 카메라·DB·설정을 모른다(numpy 도 쓰지 않는다).
vision(counter)·mock·rollup·관리 앱이 같은 규칙으로 data/zones.json 을 읽고 검증한다.

좌표계: 바닥 0~1 정규화. x = 폭(창가 통로 벽이 0), y = 길이(배식구 벽이 0). 실제 m 는 floor.width_m·length_m.
읽기: load_zones(path) 는 git 템플릿 zones.json 위에 같은 폴더의 미추적 zones.local.json(관리 앱만 쓴다 — calibrate 도 관리 앱의 한 탭)을
      최상위 키 단위로 덮어 쓴다 — Pi 체크아웃을 dirty 로 만들지 않기 위해(CLAUDE.md §2 'Pi 는 git pull 만').
구역 판정: zones 는 순서 있는 리스트, 첫 일치 우선. 여기서 나가는 것은 구역별 인원수뿐 — 개별 좌표는 어디에도 남기지 않는다.
"""
import json
import math
import re
from pathlib import Path

VERSION = 1
LOCAL_NAME = "zones.local.json"
MAX_BYTES = 64 * 1024
MAX_ZONES = 12
MIN_AREA = 1e-4            # 정규화 면적. 이보다 작으면 점·선에 가까운 폴리곤
REPROJ_TOL = 0.01          # calib_points 재투영 오차 상한(정규화 단위 — 폭 기준 약 15cm)
ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,15}$")
KEYS = {"version", "updated_at", "updated_by", "note", "floor", "camera",
        "calib_points", "image_to_floor", "buffer_px", "roi", "zones"}
ZONE_KEYS = {"id", "name", "polygon"}
ROI_KEYS = {"polygon", "lambda_edge", "out_dir"}


# ---- 읽기 -----------------------------------------------------------------------

def load_zones(path, local=None):
    """zones.json 을 읽고, zones.local.json 이 있으면 최상위 키를 덮어 쓴 뒤 검증한다. 문제가 있으면 ValueError"""
    path = Path(path)
    local = Path(local) if local else path.with_name(LOCAL_NAME)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"{path.name}: 문서가 객체가 아니다")
    if local.is_file():
        over = json.loads(local.read_text(encoding="utf-8"))
        if not isinstance(over, dict):
            raise ValueError(f"{local.name}: 문서가 객체가 아니다")
        doc.update(over)
    errors = validate_zones(doc)
    if errors:
        raise ValueError(f"{path.name}: " + "; ".join(errors))
    return doc


# ---- 검증 -----------------------------------------------------------------------

def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _point(p):
    return isinstance(p, list) and len(p) == 2 and all(_num(v) and 0 <= v <= 1 for v in p)


def _matrix3(h):
    return (isinstance(h, list) and len(h) == 3
            and all(isinstance(r, list) and len(r) == 3 and all(_num(v) for v in r) for r in h))


def _polygon_errors(poly):
    if not isinstance(poly, list) or len(poly) < 3:
        return ["꼭짓점이 3개 이상이어야 한다"]
    if not all(_point(p) for p in poly):
        return ["꼭짓점은 [x, y] 이고 0~1 범위여야 한다"]
    e = []
    if polygon_area(poly) <= MIN_AREA:
        e.append("면적이 너무 작다")
    if not is_simple(poly):
        e.append("변끼리 교차한다")
    return e


def validate_zones(doc):
    """스키마 검증. 오류 문장 리스트를 돌려준다(빈 리스트 = 통과). 예외를 던지지 않는다 — 관리 앱이 422 본문으로 그대로 쓴다"""
    if not isinstance(doc, dict):
        return ["문서가 객체가 아니다"]
    e = []
    if doc.get("version") != VERSION:
        e.append(f"version 은 {VERSION} 이어야 한다")
    unknown = set(doc) - KEYS
    if unknown:
        e.append("미지 키: " + ", ".join(sorted(unknown)))
    if len(json.dumps(doc, ensure_ascii=False).encode("utf-8")) > MAX_BYTES:
        e.append(f"문서가 {MAX_BYTES // 1024}KB 를 넘는다")
    for k in ("updated_at", "updated_by"):
        if doc.get(k) is not None and not isinstance(doc[k], str):
            e.append(f"{k} 는 문자열 또는 null")
    if "note" in doc and not isinstance(doc["note"], str):
        e.append("note 는 문자열")

    floor = doc.get("floor")
    if not (isinstance(floor, dict) and all(_num(floor.get(k)) and floor[k] > 0 for k in ("width_m", "length_m"))):
        e.append("floor.width_m·length_m 는 양수")
    if doc.get("camera") is not None and not isinstance(doc["camera"], dict):
        e.append("camera 는 객체 또는 null")
    if doc.get("buffer_px") is not None and not (_int(doc["buffer_px"]) and doc["buffer_px"] >= 0):
        e.append("buffer_px 는 0 이상의 정수")

    zones = doc.get("zones")
    if not (isinstance(zones, list) and zones):
        e.append("zones 는 비어 있지 않은 리스트")
    else:
        if len(zones) > MAX_ZONES:
            e.append(f"zones 는 {MAX_ZONES}개 이하")
        seen = set()
        for i, z in enumerate(zones):
            tag = f"zones[{i}]"
            if not (isinstance(z, dict) and set(z) == ZONE_KEYS):
                e.append(f"{tag}: id·name·polygon 세 키만")
                continue
            zid = z["id"]
            if not (isinstance(zid, str) and ID_RE.match(zid)):
                e.append(f"{tag}: id 는 소문자로 시작하는 [a-z0-9_] 16자 이하")
            elif zid in seen:
                e.append(f"{tag}: id 중복 '{zid}'")
            seen.add(zid)
            if not (isinstance(z["name"], str) and z["name"]):
                e.append(f"{tag}: name 은 빈 문자열이 아닌 문자열")
            e += [f"{tag}.polygon: {m}" for m in _polygon_errors(z["polygon"])]

    roi = doc.get("roi")
    if roi is not None:
        if not (isinstance(roi, dict) and set(roi) == ROI_KEYS):
            e.append("roi 는 polygon·lambda_edge·out_dir 세 키")
        else:
            pe = _polygon_errors(roi["polygon"])
            e += [f"roi.polygon: {m}" for m in pe]
            n = len(roi["polygon"]) if not pe else 0
            le = roi["lambda_edge"]
            if not (n and isinstance(le, list) and len(le) == 2 and all(_int(v) and 0 <= v < n for v in le)
                    and (le[1] - le[0]) % n in (1, n - 1)):
                e.append("roi.lambda_edge 는 인접한 두 꼭짓점 번호 [i, j]")
            if roi["out_dir"] not in (1, -1):
                e.append("roi.out_dir 는 1(λ선 i→j 의 왼쪽이 출구) 또는 -1(오른쪽)")

    cp = doc.get("calib_points")
    cp_ok = False
    if cp is not None:
        cp_ok = (isinstance(cp, list) and len(cp) == 4
                 and all(isinstance(p, dict) and set(p) == {"img", "floor"} and _point(p["img"]) and _point(p["floor"])
                         for p in cp))
        if not cp_ok:
            e.append("calib_points 는 {img:[u,v], floor:[x,y]} 4개 (모두 0~1 정규화)")
    h = doc.get("image_to_floor")
    if h is not None:
        if not _matrix3(h):
            e.append("image_to_floor 는 3×3 유한 수 행렬")
        elif abs(det3(h)) <= 1e-12:
            e.append("image_to_floor 가 특이 행렬이다")
        elif cp_ok:
            err = max(math.dist(project(h, *p["img"]), p["floor"]) for p in cp)
            if err >= REPROJ_TOL:
                e.append(f"calib_points 재투영 오차 {err:.4f} ≥ {REPROJ_TOL}")
    return e


# ---- 기하 -----------------------------------------------------------------------

def polygon_area(poly):
    """정규화 좌표의 면적(신발끈 공식, 절댓값)"""
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def polygon_area_m2(poly, floor):
    """실제 면적 m². 정규화 → m 는 축마다 배율이 다른 선형 변환이라 면적은 width×length 배가 된다"""
    return polygon_area(poly) * floor["width_m"] * floor["length_m"]


def _orient(a, b, c):
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)


def _on_segment(a, b, p):
    return (min(a[0], b[0]) - 1e-12 <= p[0] <= max(a[0], b[0]) + 1e-12
            and min(a[1], b[1]) - 1e-12 <= p[1] <= max(a[1], b[1]) + 1e-12)


def segments_intersect(a, b, c, d):
    """선분 ab 와 cd 가 만나는가(끝점이 닿는 것·겹치는 것도 포함)"""
    o1, o2, o3, o4 = _orient(a, b, c), _orient(a, b, d), _orient(c, d, a), _orient(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return ((o1 == 0 and _on_segment(a, b, c)) or (o2 == 0 and _on_segment(a, b, d))
            or (o3 == 0 and _on_segment(c, d, a)) or (o4 == 0 and _on_segment(c, d, b)))


def is_simple(poly):
    """단순 다각형인가 — 이웃하지 않는 변끼리 만나지 않아야 한다"""
    n = len(poly)
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):      # 이웃한 변은 꼭짓점을 공유하므로 제외
                continue
            if segments_intersect(poly[i], poly[(i + 1) % n], poly[j], poly[(j + 1) % n]):
                return False
    return True


def point_in_polygon(x, y, poly):
    """짝홀 규칙(ray casting). 아래·왼쪽 경계는 안, 위·오른쪽 경계는 밖 — 맞닿은 구역이 한 점을 두 번 세지 않게"""
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < xi + (y - yi) * (xj - xi) / (yj - yi):
            inside = not inside
        j = i
    return inside


def _xy(p):
    return (p["x"], p["y"]) if isinstance(p, dict) else (p[0], p[1])


def zone_of(x, y, zones):
    """점이 속한 구역 id. 순서대로 첫 일치, 어디에도 없으면 None"""
    for z in zones:
        if point_in_polygon(x, y, z["polygon"]):
            return z["id"]
    return None


def count_by_zone(points, zones):
    """구역별 인원수 {id: n}. 모든 구역이 키로 들어간다(0 포함). 점은 {x,y} 또는 (x,y)"""
    counts = {z["id"]: 0 for z in zones}
    for p in points:
        zid = zone_of(*_xy(p), zones)
        if zid is not None:
            counts[zid] += 1
    return counts


# ---- 밀집도 격자 (09-03 사용자 요청: 최근 30분 히트맵) --------------------------------------
# 바닥을 GRID_COLS × GRID_ROWS 셀로 나눈 인원수 — 약 3.1m × 3.1m. 구역 인원수와 같은 성격의 집계 숫자이며(CLAUDE.md §2 히트맵 행),
# 셀 번호 = row * GRID_COLS + col. 개별 좌표·궤적은 여기서도 남지 않는다.
GRID_COLS, GRID_ROWS = 5, 8


def cell_of(x, y, cols=GRID_COLS, rows=GRID_ROWS):
    """정규화 좌표 → 셀 번호. 1.0 은 마지막 셀에 넣는다(경계 밖으로 새지 않게)"""
    c = min(cols - 1, max(0, int(x * cols)))
    r = min(rows - 1, max(0, int(y * rows)))
    return r * cols + c


def count_by_cell(points, cols=GRID_COLS, rows=GRID_ROWS):
    """셀별 인원수 {cell: n} — 0 인 셀은 넣지 않는다(저장량)"""
    counts = {}
    for p in points:
        k = cell_of(*_xy(p), cols, rows)
        counts[k] = counts.get(k, 0) + 1
    return counts


# ---- 호모그래피 (이미지 → 바닥) ------------------------------------------------------

def _solve(a, b):
    """가우스 소거(부분 피벗). 정방 행렬 a·x = b. 특이하면 ValueError"""
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            raise ValueError("점 배치가 퇴화했다(세 점이 한 줄에 있거나 겹친다)")
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] for i in range(n)]


def homography_from_4(src, dst):
    """네 쌍의 대응점(src[i] → dst[i]) 으로 3×3 호모그래피(h33=1). calibrate 가 이미지 4점 ↔ 바닥 4점으로 부른다"""
    if len(src) != 4 or len(dst) != 4:
        raise ValueError("대응점은 정확히 4쌍")
    rows, rhs = [], []
    for (u, v), (x, y) in zip(src, dst):
        rows.append([u, v, 1, 0, 0, 0, -x * u, -x * v]); rhs.append(x)
        rows.append([0, 0, 0, u, v, 1, -y * u, -y * v]); rhs.append(y)
    h = _solve(rows, rhs) + [1.0]
    return [h[0:3], h[3:6], h[6:9]]


def project(h, u, v):
    """이미지 좌표 (u, v) → 바닥 좌표 (x, y)"""
    w = h[2][0] * u + h[2][1] * v + h[2][2]
    if abs(w) < 1e-12:
        raise ValueError("소실선 위의 점은 투영할 수 없다")
    return ((h[0][0] * u + h[0][1] * v + h[0][2]) / w,
            (h[1][0] * u + h[1][1] * v + h[1][2]) / w)


def det3(h):
    return (h[0][0] * (h[1][1] * h[2][2] - h[1][2] * h[2][1])
            - h[0][1] * (h[1][0] * h[2][2] - h[1][2] * h[2][0])
            + h[0][2] * (h[1][0] * h[2][1] - h[1][1] * h[2][0]))


def invert(h):
    """역행렬(바닥 → 이미지). 관리 화면이 평면도의 구역을 프레임 위에 겹쳐 그릴 때 쓴다"""
    d = det3(h)
    if abs(d) < 1e-12:
        raise ValueError("특이 행렬")
    a, b, c = h[0]
    d_, e, f = h[1]
    g, hh, i = h[2]
    return [[(e * i - f * hh) / d, (c * hh - b * i) / d, (b * f - c * e) / d],
            [(f * g - d_ * i) / d, (a * i - c * g) / d, (c * d_ - a * f) / d],
            [(d_ * hh - e * g) / d, (b * g - a * hh) / d, (a * e - b * d_) / d]]
