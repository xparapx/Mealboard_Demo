"""워치독 — 관리 포트가 실수로 공개 Funnel 에 물리면 60초 안에 스스로 잠근다 (PLAN §4.1).
`tailscale serve status --json` 을 읽어 Funnel(AllowFunnel) 이 켜진 호스트:포트의 핸들러가 127.0.0.1:ADMIN_PORT 를 가리키는지 본다.
판정(exposed)은 순수 함수 — 실제 명령은 server.py 의 주기 작업이 돌린다."""
import json


def exposed(status_json, admin_port):
    """serve status JSON(dict 또는 문자열) 에서 Funnel 로 열린 경로 중 관리 포트로 프록시하는 것이 있으면 True.
    JSON 형식은 Tailscale 판마다 조금 다르다 — 'AllowFunnel' 아래 켜진 hostport 와 'Web' 의 Handlers[].Proxy 를 보는 보수적 판정"""
    try:
        st = json.loads(status_json) if isinstance(status_json, str) else (status_json or {})
    except ValueError:
        return False
    funnel_on = {hp for hp, on in (st.get("AllowFunnel") or {}).items() if on}
    if not funnel_on:
        return False
    needle = f":{admin_port}"
    for hostport, web in (st.get("Web") or {}).items():
        if hostport not in funnel_on:
            continue
        for h in (web.get("Handlers") or {}).values():
            proxy = str(h.get("Proxy", "")) if isinstance(h, dict) else ""
            if proxy.rstrip("/").endswith(needle):
                return True
    # TCP 포워딩(tailscale funnel <port>) 형태도 본다
    for hostport, tcp in (st.get("TCP") or {}).items():
        if hostport in funnel_on and isinstance(tcp, dict) and str(tcp.get("TCPForward", "")).endswith(needle):
            return True
    return False
