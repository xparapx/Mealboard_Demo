"""관리자 신원 판정(PLAN §4.1). 요청 객체 없이 dict 만으로 돈다 — fail-closed 가 핵심."""
import pytest

from app.admin.auth import identify, parse_users

USERS = parse_users("Teacher@Example.com, dev@example.com")
KEY = "0123456789abcdef"


def test_허용목록은_소문자로_비교():
    assert USERS == {"teacher@example.com", "dev@example.com"}
    assert parse_users("") == set() and parse_users(None) == set()


def test_funnel_요청은_누구든_거부():
    ident, why = identify({"Tailscale-Funnel-Request": "?1", "Tailscale-User-Login": "teacher@example.com"}, {}, {}, USERS, KEY)
    assert ident is None and why == "funnel"


def test_lockdown_이면_거부():
    ident, why = identify({"Tailscale-User-Login": "teacher@example.com"}, {}, {}, USERS, KEY, lockdown=True)
    assert ident is None and why == "lockdown"


def test_tailscale_허용목록_통과_헤더_대소문자_무관():
    ident, why = identify({"tailscale-user-login": "Teacher@Example.com"}, {}, {}, USERS, KEY)
    assert ident == {"user": "teacher@example.com", "via": "tailscale"} and why == "ok"


def test_tailscale_신원이_있는데_목록에_없으면_키로_우회하지_못한다():
    ident, why = identify({"Tailscale-User-Login": "stranger@example.com"}, {}, {"key": KEY}, USERS, KEY)
    assert ident is None and why == "not_allowed"


def test_허용목록이_비어_있으면_tailnet_경로는_닫힘():
    ident, why = identify({"Tailscale-User-Login": "teacher@example.com"}, {}, {}, set(), KEY)
    assert ident is None and why == "closed"


@pytest.mark.parametrize("cookies, query", [({"mb_admin": KEY}, {}), ({}, {"key": KEY})])
def test_로컬_키는_쿠키나_쿼리로(cookies, query):
    ident, why = identify({}, cookies, query, USERS, KEY)
    assert ident == {"user": "local", "via": "local"} and why == "ok"


def test_틀린_키와_빈_키():
    assert identify({}, {}, {"key": "wrong"}, USERS, KEY) == (None, "bad_key")
    assert identify({}, {}, {"key": KEY}, USERS, "") == (None, "closed")     # 키가 설정돼 있지 않으면 닫힘
    assert identify({}, {}, {}, USERS, KEY) == (None, "bad_key")


def test_cloudflare_경로는_access_결과만_본다():
    # 통과: 검증된 이메일이 목록에 있음
    ident, why = identify({"cf-ray": "x"}, {}, {}, USERS, KEY, access=("ok", "teacher@example.com"))
    assert ident == {"user": "teacher@example.com", "via": "access"} and why == "ok"
    # 위조 Tailscale 헤더·로컬 키가 같이 와도 Access 결과가 없으면 거부 (터널로 들어온 외부 트래픽)
    for acc in (("no_token", None), ("bad_token", None), ("closed", None)):
        ident, why = identify({"cf-ray": "x", "Tailscale-User-Login": "teacher@example.com"}, {"mb_admin": KEY}, {"key": KEY}, USERS, KEY, access=acc)
        assert ident is None and why == acc[0]
    # 검증됐지만 목록 밖
    assert identify({}, {}, {}, USERS, KEY, access=("ok", "stranger@example.com")) == (None, "not_allowed")
    assert identify({}, {}, {}, set(), KEY, access=("ok", "teacher@example.com")) == (None, "closed")
    # Funnel·lockdown 은 Access 보다 앞선다
    assert identify({"Tailscale-Funnel-Request": "?1"}, {}, {}, USERS, KEY, access=("ok", "teacher@example.com"))[1] == "funnel"
    assert identify({}, {}, {}, USERS, KEY, lockdown=True, access=("ok", "teacher@example.com"))[1] == "lockdown"


def test_아무것도_없으면_거부():
    assert identify({}, {}, {}, set(), "")[0] is None
