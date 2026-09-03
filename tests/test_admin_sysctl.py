"""명령 허용목록 — sudoers 드롭인과 한 쌍인지, 목록 밖 명령이 막히는지."""
import pathlib
import re

import pytest

from app.admin import sysctl, watchdog

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_sudoers_파일은_허용목록과_같다():
    text = (ROOT / "deploy" / "sudoers-mealboard").read_text(encoding="utf-8")
    body = " ".join(line.strip().rstrip("\\").strip() for line in text.splitlines() if not line.startswith("#"))
    listed = {tuple(c.strip().replace("/usr/bin/", "").split()) for c in body.split("NOPASSWD:")[1].split(",")}
    assert listed == set(sysctl.ALLOWED_SUDO)
    assert "*" not in text and "ALL=(ALL)" not in text                 # 와일드카드·전권 없음


def test_관리_앱_자신은_재시작_목록에_없다():
    assert "admin" not in sysctl.RESTARTABLE
    assert not any("mealboard-admin" in " ".join(a) for a in sysctl.ALLOWED_SUDO)
    assert not any("reset" in a for a in sysctl.ALLOWED_SUDO)


def test_허용목록_밖_sudo_명령은_만들어지지_않는다():
    with pytest.raises(PermissionError):
        sysctl.run(("systemctl", "stop", "mealboard-api.service"), sudo=True)
    with pytest.raises(PermissionError):
        sysctl.restart("admin")
    with pytest.raises(PermissionError):
        sysctl.start_job("api")
    with pytest.raises(PermissionError):
        sysctl.journal("sshd", 10)


def test_없는_명령은_rc_127():
    rc, out, err = sysctl.run(("definitely-not-a-command-xyz", "--v"))
    assert rc == 127 and "없다" in err


def test_로그_줄_수는_500_으로_눌린다():
    # journalctl 이 없는 개발 PC 에서도 인자 검증은 먼저 돈다
    rc, text = sysctl.journal("mealboard-api", 99999)
    assert rc in (0, 127)


def test_워치독은_관리_포트가_funnel_에_물릴_때만():
    exposed = {"AllowFunnel": {"rsp.taild5f11e.ts.net:443": True, "rsp.taild5f11e.ts.net:8443": False},
               "Web": {"rsp.taild5f11e.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8101"}}},
                       "rsp.taild5f11e.ts.net:8443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8101"}}}}}
    safe = {"AllowFunnel": {"rsp.taild5f11e.ts.net:443": True},
            "Web": {"rsp.taild5f11e.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8100"}}},
                    "rsp.taild5f11e.ts.net:8443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8101"}}}}}
    assert watchdog.exposed(exposed, 8101)
    assert not watchdog.exposed(safe, 8101)
    assert not watchdog.exposed("{broken", 8101) and not watchdog.exposed({}, 8101)
    tcp = {"AllowFunnel": {"h:10000": True}, "TCP": {"10000": {"TCPForward": "127.0.0.1:8101"}}}   # 실제 JSON: TCP 는 포트만 키
    assert watchdog.exposed(tcp, 8101)
    assert not watchdog.exposed({"AllowFunnel": {"h:443": True}, "TCP": {"10000": {"TCPForward": "127.0.0.1:8101"}}}, 8101)


def test_sudoers_본문_생성기는_같은_목록에서_나온다():
    lines = sysctl.sudo_lines("xparapx")
    assert lines[0].startswith("xparapx ALL=(root) NOPASSWD:")
    assert len(re.findall(r"/usr/bin/", lines[0])) == len(sysctl.ALLOWED_SUDO)
