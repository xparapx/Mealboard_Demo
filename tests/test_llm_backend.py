"""LLM 백엔드 교체 구조(10-20, 공모전 '모델 비종속') — 엔진 선택 규칙, OpenAI 호환 백엔드의 요청·응답·오류 매핑, 추론 태그 제거.
네트워크 없이 urlopen 을 가짜로 바꾼다."""
import io
import json
import urllib.error

import pytest

from jobs.llm import LLMBusy, LLMUnavailable, LocalLLM, _openai_backend, resolve_backend, strip_think


def test_resolve_backend_auto():
    assert resolve_backend("auto", hef="", model="") == "none"
    assert resolve_backend("auto", hef="/x.hef", model="") == "hailo"
    assert resolve_backend("auto", hef="", model="gemma4:e2b") == "openai"
    assert resolve_backend("auto", hef="/x.hef", model="gemma4:e2b") == "hailo"      # 둘 다 있으면 장치 우선
    assert resolve_backend("openai", hef="/x.hef", model="m") == "openai"            # 명시가 이긴다
    assert resolve_backend("none", hef="/x.hef", model="m") == "none"


def test_strip_think():
    assert strip_think("<think>생각 중…</think>\n{\"a\": 1}") == '{"a": 1}'
    assert strip_think("앞글 <think>미완") == "앞글"
    assert strip_think("그대로") == "그대로"
    assert strip_think(None) is None


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_openai_backend_request_and_parse(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        seen["body"] = json.loads(req.data.decode("utf-8"))
        seen["timeout"] = timeout
        return _Resp(json.dumps({"choices": [{"message": {"content": "<think>x</think>Line 1\nLine 2"}}]}).encode("utf-8"))
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    complete, close = _openai_backend("http://127.0.0.1:11434/v1/", "gemma4:e2b", key="")
    out = complete("sys", "user", 64, 0.0, 30)
    assert out == "Line 1\nLine 2"
    assert seen["url"] == "http://127.0.0.1:11434/v1/chat/completions" and seen["timeout"] == 30
    assert seen["body"]["model"] == "gemma4:e2b" and seen["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert seen["body"]["max_tokens"] == 64 and seen["body"]["stream"] is False
    assert "Authorization" not in seen["headers"]                                    # Ollama 는 키 없음
    close()
    complete2, _ = _openai_backend("https://api.openai.com/v1", "gpt-4o-mini", key="sk-test")
    complete2("s", "u", 8, 0.0, 10)
    assert seen["headers"].get("Authorization") == "Bearer sk-test"


def test_openai_backend_errors(monkeypatch):
    import urllib.request

    def http_err(code):
        def f(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, code, "err", {}, io.BytesIO(b"busy"))
        return f
    complete, _ = _openai_backend("http://127.0.0.1:11434/v1", "m")
    monkeypatch.setattr(urllib.request, "urlopen", http_err(429))
    with pytest.raises(LLMBusy):
        complete("s", "u", 8, 0.0, 5)
    monkeypatch.setattr(urllib.request, "urlopen", http_err(404))
    with pytest.raises(LLMUnavailable):
        complete("s", "u", 8, 0.0, 5)

    def refused(req, timeout=None):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(urllib.request, "urlopen", refused)
    with pytest.raises(LLMUnavailable):
        complete("s", "u", 8, 0.0, 5)
    with pytest.raises(LLMUnavailable):
        _openai_backend("http://x/v1", "")                                            # 모델 이름 없음


def test_local_llm_engine_selection(monkeypatch):
    m = LocalLLM(engine="openai", model="exaone4.0:1.2b", base_url="http://127.0.0.1:11434/v1", api_key="")
    assert m.engine == "openai" and m.model == "exaone4.0:1.2b"
    with pytest.raises(LLMUnavailable):
        with LocalLLM(engine="none"):
            pass
    fake = LocalLLM(hef="fake-model.hef", backend=lambda s, u, mt, t, to: "ok")       # 테스트용 가짜는 hailo 로 본다(기존 테스트 호환)
    assert fake.engine == "hailo" and fake.model == "fake-model"
    with fake as f:
        assert f.complete("s", "u") == "ok"
