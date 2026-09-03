"""구역 정의 저장 — `data/zones.local.json` 의 유일한 writer 는 관리 앱이다 (CLAUDE.md §2). git 템플릿 `zones.json` 은 절대 쓰지 않는다
('Pi 는 git pull 만'). 읽기는 vision/zones.load_zones(템플릿 + local overlay)와 같은 규칙 — 편집기가 보는 것이 vision·mock·rollup 이 보는 것이다.
쓰기: validate_zones 를 통과한 문서 **전체**를 local 에 `.tmp → os.replace`(원자적), 직전 local 은 `.bak-<시각>` 으로 최신 KEEP_BAK 개 보존.
호모그래피: 이미지 4점 ↔ 바닥 4점(모두 0~1 정규화) → image_to_floor(3×3) + 역행렬 + 재투영 오차."""
import datetime as dt
import json
import math
import os
import shutil
import time

from ..config import ZONES_JSON
from vision.zones import LOCAL_NAME, REPROJ_TOL, det3, homography_from_4, invert, load_zones, project, validate_zones

TEMPLATE = ZONES_JSON
LOCAL = ZONES_JSON.with_name(LOCAL_NAME)
KEEP_BAK = 5


class Invalid(ValueError):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


def _iso(ts):
    return dt.datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def backups(local=None):
    local = local or LOCAL
    return sorted((p.name for p in local.parent.glob(local.name + ".bak-*")), reverse=True)


def read(template=None, local=None):
    """→ {doc, local(bool), local_mtime, template_mtime, backups}. 템플릿·local 이 깨졌으면 ValueError/OSError 그대로"""
    template, local = template or TEMPLATE, local or LOCAL
    doc = load_zones(template, local)
    return {"doc": doc, "local": local.is_file(),
            "local_mtime": _iso(local.stat().st_mtime) if local.is_file() else None,
            "template_mtime": _iso(template.stat().st_mtime), "backups": backups(local)}


def _replace(tmp, dst):
    """Windows 에서는 읽는 순간 replace 가 거부될 수 있어 잠깐 재시도 (mock_feed.write_positions 와 같은 이유)"""
    for _ in range(10):
        try:
            os.replace(tmp, dst)
            return
        except PermissionError:
            time.sleep(0.02)
    os.replace(tmp, dst)


def write(doc, user, template=None, local=None, now=None):
    """검증 → 백업 → 원자적 쓰기. → (병합된 doc, 백업 파일명 또는 None). 검증 실패는 Invalid(errors).
    local 에는 **템플릿과 다른 최상위 키만** 남긴다(+ updated_at/by) — overlay 는 키 단위이므로, 손대지 않은 키(version·floor·note…)는
    계속 git 템플릿을 따른다. 전체를 쓰면 첫 저장 뒤 템플릿 갱신이 영영 닿지 않고 VERSION 을 올렸을 때 모든 읽기가 죽는다"""
    template, local = template or TEMPLATE, local or LOCAL
    if not isinstance(doc, dict):
        raise Invalid(["문서가 객체가 아니다"])
    tpl = json.loads(template.read_text(encoding="utf-8"))
    doc = {**tpl, **doc}                                   # 빠진 키는 템플릿 값으로 채워 검증한다
    now = now or dt.datetime.now()
    doc["updated_at"] = now.isoformat(timespec="seconds")
    doc["updated_by"] = user
    doc.pop("version", None); doc["version"] = tpl.get("version")     # version 은 언제나 템플릿의 것
    errors = validate_zones(doc)
    if errors:
        raise Invalid(errors)
    over = {k: v for k, v in doc.items() if k in ("updated_at", "updated_by") or (k != "version" and tpl.get(k) != v)}
    bak = None
    if local.is_file():
        bak = f"{local.name}.bak-{now.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(local, local.with_name(bak))
        for old in backups(local)[KEEP_BAK:]:                 # 최신 KEEP_BAK 개만 — 이 도구가 만든 백업만 지운다
            local.with_name(old).unlink(missing_ok=True)
    tmp = local.with_name(local.name + ".tmp")
    tmp.write_text(json.dumps(over, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        _replace(tmp, local)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return doc, bak


def _pair_ok(p):
    return (isinstance(p, dict) and set(p) == {"img", "floor"}
            and all(isinstance(p[k], list) and len(p[k]) == 2
                    and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and 0 <= v <= 1 for v in p[k])
                    for k in ("img", "floor")))


def homography(pairs):
    """pairs = [{img:[u,v], floor:[x,y]}×4] → {image_to_floor, floor_to_image, reproj_err, ok}. 형태·퇴화는 Invalid"""
    if not (isinstance(pairs, list) and len(pairs) == 4 and all(_pair_ok(p) for p in pairs)):
        raise Invalid(["pairs 는 {img:[u,v], floor:[x,y]} 4개 (모두 0~1 정규화)"])
    try:
        h = homography_from_4([p["img"] for p in pairs], [p["floor"] for p in pairs])
    except ValueError as e:
        raise Invalid([str(e)])
    if abs(det3(h)) <= 1e-12:
        raise Invalid(["결과가 특이 행렬이다"])
    err = max(math.dist(project(h, *p["img"]), p["floor"]) for p in pairs)
    return {"image_to_floor": h, "floor_to_image": invert(h), "reproj_err": round(err, 6), "ok": err < REPROJ_TOL, "tol": REPROJ_TOL}
