"""Cloudflare Access 신원 검증 — `admin.kjhs-meal.com` 경로(09-11 사용자 결정).

Cloudflare 는 Access 로그인(이메일 일회용 코드)을 통과한 요청에만 `Cf-Access-Jwt-Assertion` 헤더(RS256 JWT)를 붙여 터널로 넘긴다.
여기서는 그 JWT 를 팀 도메인의 공개키(JWKS, https://<team>/cdn-cgi/access/certs)로 서명·aud·iss·만료를 검증하고 `email` 만 돌려준다.
설정(`.env CF_ACCESS_TEAM`·`CF_ACCESS_AUD`)이 비어 있으면 이 경로는 닫힌다(fail-closed). 검증에 실패한 토큰은 어떤 다른 신원으로도 물러서지 않는다.

Cloudflare 를 거쳐 온 요청은 게이트(server.py)가 `cf-ray` 헤더 또는 이 JWT 헤더로 알아본다 — 그 요청에서는 Tailscale 헤더·로컬 키를 보지 않는다.
터널이 8101 로 외부 트래픽을 넘기는 순간부터 위조 `Tailscale-User-Login` 이 실제 위협이 되기 때문이다(PLAN §7 loopback 헤더 위조)."""
import jwt

HEADER = "cf-access-jwt-assertion"
JWKS_LIFESPAN = 3600      # 공개키 캐시(초). Cloudflare 는 키를 드물게 돌린다 — kid 가 없으면 PyJWKClient 가 다시 받는다


def team_url(team):
    """'mealboard.cloudflareaccess.com' | 'https://mealboard.cloudflareaccess.com/' → 'https://mealboard.cloudflareaccess.com'"""
    t = (team or "").strip().rstrip("/")
    if not t:
        return ""
    return t if t.startswith("https://") else "https://" + t


class AccessVerifier:
    """check(token) → (status, email). status: 'ok' | 'closed'(미설정) | 'no_token' | 'bad_token'. 순수하게 쓰려면 jwks 에 대역을 넣는다"""

    def __init__(self, team, aud, jwks=None):
        self.issuer = team_url(team)
        self.aud = (aud or "").strip()
        self.jwks = jwks
        if self.enabled and self.jwks is None:
            self.jwks = jwt.PyJWKClient(self.issuer + "/cdn-cgi/access/certs", cache_keys=True, lifespan=JWKS_LIFESPAN)

    @property
    def enabled(self):
        return bool(self.issuer and self.aud)

    def check(self, token):
        if not self.enabled:
            return "closed", None
        if not token:
            return "no_token", None
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.aud, issuer=self.issuer,
                                options={"require": ["exp", "iat", "aud", "iss"]})
        except (jwt.PyJWTError, ValueError, OSError):        # 서명·aud·iss·만료·형식·JWKS 수신 실패 — 전부 같은 거부
            return "bad_token", None
        email = str(claims.get("email") or "").strip().lower()
        return ("ok", email) if email else ("bad_token", None)
