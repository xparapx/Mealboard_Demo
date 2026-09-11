"""관리자 신원 판정 — 순수 함수. 요청 헤더·쿠키·쿼리와 설정만 보고 (신원, 거부 사유) 를 돌려준다 (PLAN §4.1, fail-closed).

순서:
  ① `Tailscale-Funnel-Request` 헤더가 있으면 거부 — 공개 Funnel 을 통해 들어온 요청은 누구든 관리자가 아니다
  ② lockdown(워치독이 "관리 포트가 Funnel 에 물렸다"고 판단한 상태)이면 거부
  ②' Cloudflare 를 거쳐 온 요청(access 인자가 None 이 아님 — 게이트가 cf-ray·Access JWT 헤더로 판별)은 **Access 검증 결과만** 본다:
     ('ok', email) 이고 email 이 허용목록에 있으면 via=access, 그 밖(미설정·토큰 없음·검증 실패·목록 밖)은 거부. 이 경로에서는 Tailscale 헤더·로컬 키를 보지 않는다 —
     터널이 8101 로 외부 트래픽을 넘기므로 위조 헤더가 실제 위협(09-11, PLAN §7 loopback 헤더 위조)
  ③ `Tailscale-User-Login` 이 허용목록(ADMIN_USERS, 소문자 비교)에 있으면 via=tailscale. 목록이 비어 있으면 닫힘
  ④ Tailscale 헤더가 없으면 쿠키 `mb_admin` 또는 `?key=` 가 ADMIN_LOCAL_KEY 와 상수시간 일치할 때 via=local (SSH 터널 경로).
     키가 비어 있으면 닫힘. loopback 판정은 하지 않는다 — Serve 도 터널도 모두 127.0.0.1 로 들어온다
  ⑤ 그 밖엔 거부
헤더 이름은 대소문자를 가리지 않는다. Tailscale 헤더가 있는데 목록에 없으면 로컬 키로 물러서지 않는다(신원이 있는데 키로 우회하는 길을 막는다)."""
import hmac

COOKIE = "mb_admin"


def parse_users(text):
    """ADMIN_USERS='a@x.com, B@y.com' → {'a@x.com', 'b@y.com'}"""
    return {u.strip().lower() for u in (text or "").split(",") if u.strip()}


def _get(mapping, key):
    """헤더처럼 대소문자를 가리지 않는 조회. 없으면 None"""
    if mapping is None:
        return None
    lk = key.lower()
    for k, v in mapping.items():
        if k.lower() == lk:
            return v
    return None


def identify(headers, cookies, query, users, local_key, lockdown=False, access=None):
    """→ (identity | None, reason). identity = {'user': str, 'via': 'tailscale' | 'access' | 'local'}.
    access: None(Cloudflare 경로가 아님) 또는 app/admin/access.AccessVerifier.check 의 (status, email)"""
    if _get(headers, "Tailscale-Funnel-Request") is not None:
        return None, "funnel"
    if lockdown:
        return None, "lockdown"
    if access is not None:
        status, email = access
        if status != "ok":
            return None, status                                   # closed | no_token | bad_token
        if email and email in (users or set()):
            return {"user": email, "via": "access"}, "ok"
        return None, "not_allowed" if users else "closed"
    login = _get(headers, "Tailscale-User-Login")
    if login is not None:
        login = login.strip().lower()
        if login and login in (users or set()):
            return {"user": login, "via": "tailscale"}, "ok"
        return None, "not_allowed" if users else "closed"
    key = _get(cookies, COOKIE) or _get(query, "key")
    if local_key and key and hmac.compare_digest(str(key), str(local_key)):
        return {"user": "local", "via": "local"}, "ok"
    return None, "closed" if not local_key else "bad_key"
