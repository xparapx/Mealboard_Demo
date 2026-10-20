"""관리 앱의 LLM 선택 저장소(10-20) — data/llm.local.json 의 유일한 writer. 후보 모델 목록(Hailo .hef · OpenAI 호환 서버의 모델)도 여기서 묻는다.
쓰기는 `.tmp → os.replace`(원자적), 직전 파일은 `.bak-<시각>` 으로 최신 KEEP_BAK 개. 키는 절대 저장하지 않는다."""
import datetime as dt
import json
import os
import urllib.error
import urllib.request

from ..config import DATA
from .. import llm_overlay

LOCAL = llm_overlay.LOCAL
KEEP_BAK = 5
MODELS_DIR = DATA / "models"


class Invalid(ValueError):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def validate(doc):
    errors = []
    if not isinstance(doc, dict):
        return ["문서가 객체가 아니다"]
    b = str(doc.get("backend", "")).strip()
    if b not in llm_overlay.BACKENDS:
        errors.append(f"backend 는 {'|'.join(llm_overlay.BACKENDS)} 중 하나: {b!r}")
    m = str(doc.get("model", "")).strip()
    if len(m) > 120 or any(c in m for c in "\n\r\t\"'<>"):
        errors.append("model 이름이 길거나 금지 문자가 있다")
    if b == "openai" and not m:
        errors.append("openai 백엔드는 모델 이름이 필요하다")
    u = str(doc.get("base_url", "")).strip()
    if u and not (u.startswith("http://") or u.startswith("https://")) or len(u) > 200:
        errors.append("base_url 은 http(s):// 로 시작해야 한다")
    for k in doc:
        if k not in ("backend", "model", "base_url"):
            errors.append(f"허용되지 않는 키: {k}")
    return errors


def backups(local=None):
    local = LOCAL if local is None else local
    return sorted((p.name for p in local.parent.glob(local.name + ".bak-*")), reverse=True)


def _save(doc, local, now=None):
    now = now or dt.datetime.now()
    bak = None
    if local.is_file():
        bak = f"{local.name}.bak-{now.strftime('%Y%m%d-%H%M%S')}"
        os.replace(local, local.parent / bak)
        for old in backups(local)[KEEP_BAK:]:
            (local.parent / old).unlink(missing_ok=True)
    tmp = local.parent / (local.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, local)
    return bak


def write(choice, user, local=None, now=None):
    """선택 저장 → (doc, bak). 이전 파일의 last_check 는 유지한다(선택이 같은 모델이면 비교에 유용). 검증 실패는 Invalid"""
    local = LOCAL if local is None else local
    errors = validate(choice)
    if errors:
        raise Invalid(errors)
    prev = llm_overlay.read(local)
    doc = {k: str(choice.get(k, "")).strip() for k in ("backend", "model", "base_url")}
    doc = {k: v for k, v in doc.items() if v}
    doc["updated_at"] = (now or dt.datetime.now()).isoformat(timespec="seconds")
    doc["updated_by"] = (user or {}).get("user") if isinstance(user, dict) else user
    if prev.get("last_check"):
        doc["last_check"] = prev["last_check"]
    bak = _save(doc, local, now)
    return doc, bak


def write_check(result, local=None, now=None):
    """점검 결과 요약을 같은 파일의 last_check 에 남긴다(선택은 그대로)"""
    local = LOCAL if local is None else local
    doc = llm_overlay.read(local)
    doc["last_check"] = result
    _save(doc, local, now)
    return doc


def reset(user, local=None, now=None):
    """.env 로 되돌리기 — 파일을 지우지 않고 .bak 으로 옮긴다"""
    local = LOCAL if local is None else local
    if not local.is_file():
        return None
    now = now or dt.datetime.now()
    bak = f"{local.name}.bak-{now.strftime('%Y%m%d-%H%M%S')}"
    os.replace(local, local.parent / bak)
    for old in backups(local)[KEEP_BAK:]:
        (local.parent / old).unlink(missing_ok=True)
    return bak


# ---- 후보 ----
def hef_candidates(models_dir=None):
    d = MODELS_DIR if models_dir is None else models_dir
    out = []
    try:
        for p in sorted(d.glob("*.hef")):
            out.append({"id": str(p), "label": p.stem, "kind": "hailo", "size_gb": round(p.stat().st_size / 1e9, 2)})
    except OSError:
        pass
    return out


def _get_json(url, timeout):
    with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def server_candidates(base_url, timeout=2.5):
    """OpenAI 호환 서버의 모델 목록. Ollama 는 /api/tags(크기 포함), 그 밖은 /v1/models. 닿지 않으면 reachable=False"""
    base = base_url.rstrip("/")
    root = base[:-3] if base.endswith("/v1") else base
    try:
        doc = _get_json(root + "/api/tags", timeout)
        models = [{"id": m.get("name") or m.get("model"), "label": m.get("name") or m.get("model"), "kind": "openai",
                   "size_gb": round((m.get("size") or 0) / 1e9, 2)} for m in doc.get("models", [])]
        return {"reachable": True, "server": "ollama", "models": [m for m in models if m["id"]]}
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        pass
    try:
        doc = _get_json(base + "/models", timeout)
        models = [{"id": m.get("id"), "label": m.get("id"), "kind": "openai"} for m in doc.get("data", [])]
        return {"reachable": True, "server": "openai", "models": [m for m in models if m["id"]]}
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return {"reachable": False, "server": None, "models": []}
