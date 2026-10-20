"""관리 화면 AI 모델 선택(10-20) — 오버레이 우선순위, 저장소 검증·백업·되돌리기, 후보 목록. 네트워크·장치 없음."""
import io
import json
import urllib.error

import pytest

from app import llm_overlay
from app.admin import llm_store


def test_effective_overlay_precedence():
    env = dict(backend="auto", model="", base_url="http://127.0.0.1:11434/v1")
    assert llm_overlay.effective({}, **env) == {**env, "source": "env"}
    e = llm_overlay.effective({"backend": "openai", "model": "gemma4:e2b"}, **env)
    assert e["backend"] == "openai" and e["model"] == "gemma4:e2b" and e["base_url"] == env["base_url"] and e["source"] == "local"
    e = llm_overlay.effective({"backend": "weird", "model": " "}, **env)                 # 잘못된 값은 .env 로
    assert e["backend"] == "auto" and e["model"] == "" and e["source"] == "env"


def test_store_write_validate_backup_reset(tmp_path):
    local = tmp_path / "llm.local.json"
    user = {"user": "t@example", "via": "tailscale"}
    doc, bak = llm_store.write({"backend": "openai", "model": "gemma4:e2b", "base_url": "http://127.0.0.1:11434/v1"}, user, local=local)
    assert bak is None and local.is_file() and doc["updated_by"] == "t@example"
    assert llm_overlay.read(local)["model"] == "gemma4:e2b"
    llm_store.write_check({"ok": True, "engine": "openai", "model": "gemma4:e2b", "news": {"n": 1, "pass": 1}, "report": {"n": 1, "pass": 0}}, local=local)
    doc2, bak2 = llm_store.write({"backend": "hailo"}, user, local=local)              # 선택을 바꿔도 last_check 는 남는다
    assert bak2 and (tmp_path / bak2).is_file() and doc2["last_check"]["model"] == "gemma4:e2b" and "model" not in doc2
    with pytest.raises(llm_store.Invalid):
        llm_store.write({"backend": "openai", "model": ""}, user, local=local)          # openai 는 모델 필수
    with pytest.raises(llm_store.Invalid):
        llm_store.write({"backend": "openai", "model": "x", "base_url": "ftp://x"}, user, local=local)
    with pytest.raises(llm_store.Invalid):
        llm_store.write({"backend": "none", "api_key": "sk-x"}, user, local=local)       # 키는 절대 이 파일에
    bak3 = llm_store.reset(user, local=local)
    assert bak3 and not local.is_file() and llm_overlay.read(local) == {}
    assert llm_store.reset(user, local=local) is None


def test_hef_candidates(tmp_path):
    (tmp_path / "Qwen3-1.7B-Instruct.hef").write_bytes(b"0" * 2048)
    (tmp_path / "yolo11n.pt").write_bytes(b"0")
    c = llm_store.hef_candidates(tmp_path)
    assert [x["label"] for x in c] == ["Qwen3-1.7B-Instruct"] and c[0]["kind"] == "hailo"
    assert llm_store.hef_candidates(tmp_path / "nope") == []


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_server_candidates(monkeypatch):
    import urllib.request

    def ollama(req, timeout=None):
        if req.full_url.endswith("/api/tags"):
            return _Resp(json.dumps({"models": [{"name": "gemma4:e2b", "size": 2_900_000_000}, {"name": "ingu627/exaone4.0:1.2b", "size": 812_000_000}]}).encode())
        raise urllib.error.URLError("x")
    monkeypatch.setattr(urllib.request, "urlopen", ollama)
    r = llm_store.server_candidates("http://127.0.0.1:11434/v1")
    assert r["reachable"] and r["server"] == "ollama" and [m["id"] for m in r["models"]] == ["gemma4:e2b", "ingu627/exaone4.0:1.2b"] and r["models"][0]["size_gb"] == 2.9

    def openai(req, timeout=None):
        if req.full_url.endswith("/models"):
            return _Resp(json.dumps({"data": [{"id": "gpt-4o-mini"}]}).encode())
        raise urllib.error.URLError("x")
    monkeypatch.setattr(urllib.request, "urlopen", openai)
    r = llm_store.server_candidates("https://api.openai.com/v1")
    assert r["reachable"] and r["server"] == "openai" and r["models"][0]["id"] == "gpt-4o-mini"

    def down(req, timeout=None):
        raise urllib.error.URLError("refused")
    monkeypatch.setattr(urllib.request, "urlopen", down)
    assert llm_store.server_candidates("http://127.0.0.1:11434/v1") == {"reachable": False, "server": None, "models": []}


def test_local_llm_reads_overlay(monkeypatch, tmp_path):
    from jobs import llm
    local = tmp_path / "llm.local.json"
    local.write_text(json.dumps({"backend": "openai", "model": "gemma4:e2b", "base_url": "http://127.0.0.1:11434/v1"}), encoding="utf-8")
    monkeypatch.setattr(llm_overlay, "LOCAL", local)
    m = llm.LocalLLM()
    assert m.engine == "openai" and m.model == "gemma4:e2b" and m.base_url == "http://127.0.0.1:11434/v1"
    monkeypatch.setattr(llm_overlay, "LOCAL", tmp_path / "missing.json")
    m2 = llm.LocalLLM(engine="none")
    assert m2.engine == "none"
