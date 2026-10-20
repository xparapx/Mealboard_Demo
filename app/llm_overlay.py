"""LLM 엔진 선택 오버레이(10-20, 공모전 '모델 비종속') — data/llm.local.json.
쓰는 쪽은 관리 앱(app/admin/llm_store.py)뿐, 읽는 쪽은 jobs/llm.py(LocalLLM)·관리 앱·점검 CLI. zones.local.json 과 같은 규칙:
.env(LLM_BACKEND·LLM_MODEL·LLM_BASE_URL) 위에 파일 값이 덮인다(overlay). **키(LLM_API_KEY)는 이 파일에 절대 넣지 않는다** — .env 만.
파일이 없거나 깨지면 .env 그대로다(아무것도 깨지지 않는다)."""
import json

from .config import DATA, LLM_BACKEND, LLM_BASE_URL, LLM_MODEL

LOCAL = DATA / "llm.local.json"
KEYS = ("backend", "model", "base_url")
BACKENDS = ("auto", "hailo", "openai", "none")


def read(path=None):
    """파일 전체(dict). 없거나 깨지면 {}"""
    p = LOCAL if path is None else path
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def effective(local=None, backend=LLM_BACKEND, model=LLM_MODEL, base_url=LLM_BASE_URL):
    """지금 적용되는 엔진 설정 {backend, model, base_url, source: env|local}. local 의 빈 값은 덮지 않는다"""
    local = read() if local is None else (local or {})
    out = {"backend": backend, "model": model, "base_url": base_url, "source": "env"}
    for k in KEYS:
        v = local.get(k)
        if not (isinstance(v, str) and v.strip()):
            continue
        if k == "backend" and v.strip() not in BACKENDS:
            continue                                            # 모르는 엔진 이름은 무시(.env 유지)
        out[k] = v.strip()
        out["source"] = "local"
    return out
