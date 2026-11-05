"""외부 HTTP 호출의 단일 출구(11-05, 공공 GitLab 푸시 보안 검사 대응).

urllib 은 file:// 같은 스킴도 열 수 있어 정적 분석(semgrep `dynamic-urllib-use-detected`)이 동적 URL 로 urlopen 을
부르는 모든 자리를 경고한다. 여기서 스킴을 http/https 로 제한하고 호스트가 있는지 확인한 뒤에만 urlopen 을 부른다 —
저장소의 다른 코드는 `urllib.request.urlopen` 을 직접 부르지 않고 이 함수를 쓴다.
테스트가 `urllib.request.urlopen` 을 monkeypatch 하므로 호출 시점에 모듈 속성으로 찾는다."""
import urllib.parse
import urllib.request

ALLOWED_SCHEMES = ("http", "https")


def check_url(url: str) -> str:
    """http(s) 절대 URL 만 통과. 그 밖(file·ftp·data·상대 경로)은 ValueError."""
    parts = urllib.parse.urlsplit(str(url))
    if parts.scheme not in ALLOWED_SCHEMES or not parts.netloc:
        raise ValueError(f"허용되지 않는 URL: {str(url)[:60]!r} (http/https 만)")
    return url


def urlopen(req, timeout=None):
    """urllib.request.urlopen 과 같은 서명(Request 또는 문자열 URL). 스킴 검증이 먼저다."""
    check_url(req.full_url if isinstance(req, urllib.request.Request) else req)
    # 스킴을 위에서 http/https 로 제한했다 — 정적 분석의 동적 URL 경고는 이 한 줄에서만 억제한다.
    return urllib.request.urlopen(req, timeout=timeout)  # nosemgrep
