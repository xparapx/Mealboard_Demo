"""app.net — 외부 HTTP 단일 출구(11-05): http/https 만 통과, 호출 시점 monkeypatch 호환."""
import urllib.request

import pytest

from app import net


def test_scheme_allowlist():
    assert net.check_url("https://open.neis.go.kr/hub/x") and net.check_url("http://127.0.0.1:11434/api/chat")
    for bad in ("file:///etc/passwd", "ftp://x/y", "data:text/plain,hi", "/relative", "https://", ""):
        with pytest.raises(ValueError):
            net.check_url(bad)


def test_urlopen_checks_before_calling(monkeypatch):
    seen = {}
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: seen.setdefault("url", req.full_url if hasattr(req, "full_url") else req))
    net.urlopen(urllib.request.Request("https://api.example.test/v1"), timeout=5)
    assert seen["url"] == "https://api.example.test/v1"
    with pytest.raises(ValueError):
        net.urlopen("file:///C:/Windows/win.ini")
    assert seen["url"] == "https://api.example.test/v1"                            # file:// 은 urlopen 까지 가지 않았다
