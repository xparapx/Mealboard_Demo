"""Cloudflare Access JWT 검증(app/admin/access.py). 네트워크 없이 — 테스트가 만든 RSA 키로 서명하고 JWKS 대역을 넣는다."""
import datetime as dt

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.admin.access import AccessVerifier, team_url

TEAM = "mealboard.cloudflareaccess.com"
ISS = "https://" + TEAM
AUD = "a" * 64


class FakeJWKS:
    """PyJWKClient 대역 — kid 와 무관하게 준비된 공개키를 돌려준다"""
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):
        class K:
            key = self.public_key
        return K()


@pytest.fixture(scope="module")
def keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key(), other


def token(priv, **over):
    now = dt.datetime.now(dt.timezone.utc)
    claims = {"aud": [AUD], "iss": ISS, "email": "Teacher@Example.com", "iat": now, "exp": now + dt.timedelta(minutes=5), "sub": "x"}
    claims.update(over)
    return jwt.encode(claims, priv, algorithm="RS256", headers={"kid": "k1"})


def test_team_url_정규화():
    assert team_url(TEAM) == ISS and team_url(ISS + "/") == ISS and team_url("") == "" and team_url(None) == ""


def test_미설정이면_닫힘_토큰_있어도(keys):
    priv, pub, _ = keys
    assert AccessVerifier("", AUD, jwks=FakeJWKS(pub)).check(token(priv)) == ("closed", None)
    assert AccessVerifier(TEAM, "", jwks=FakeJWKS(pub)).check(token(priv)) == ("closed", None)


def test_정상_토큰은_이메일_소문자(keys):
    priv, pub, _ = keys
    v = AccessVerifier(TEAM, AUD, jwks=FakeJWKS(pub))
    assert v.enabled and v.check(token(priv)) == ("ok", "teacher@example.com")


def test_토큰_없음(keys):
    _, pub, _ = keys
    assert AccessVerifier(TEAM, AUD, jwks=FakeJWKS(pub)).check(None) == ("no_token", None)
    assert AccessVerifier(TEAM, AUD, jwks=FakeJWKS(pub)).check("") == ("no_token", None)


@pytest.mark.parametrize("over", [
    {"aud": ["b" * 64]},                                                          # 다른 애플리케이션의 토큰
    {"iss": "https://other.cloudflareaccess.com"},                                # 다른 팀
    {"exp": dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)},         # 만료
    {"email": ""},                                                                # 이메일 없음
])
def test_거부되는_토큰(keys, over):
    priv, pub, _ = keys
    assert AccessVerifier(TEAM, AUD, jwks=FakeJWKS(pub)).check(token(priv, **over)) == ("bad_token", None)


def test_다른_키로_서명한_토큰과_쓰레기(keys):
    priv, pub, other = keys
    v = AccessVerifier(TEAM, AUD, jwks=FakeJWKS(pub))
    assert v.check(token(other)) == ("bad_token", None)
    assert v.check("not.a.jwt") == ("bad_token", None)
    none_alg = jwt.encode({"aud": [AUD], "iss": ISS, "email": "teacher@example.com"}, key=None, algorithm="none")   # alg=none 은 절대 통과 못 한다
    assert v.check(none_alg) == ("bad_token", None)
