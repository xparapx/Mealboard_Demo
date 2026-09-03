"""시스템 명령 — 허용목록에 있는 정확한 argv 만, 셸 없이. sudoers 드롭인(deploy/sudoers-mealboard)과 한 쌍이다:
여기 없는 명령은 만들 수 없고, sudoers 에 없는 명령은 sudo 가 거부한다. 읽기 명령(is-active·show·journalctl)은 sudo 없이 돈다
(journalctl 은 systemd-journal 그룹). 개발 PC(Windows)에는 명령이 없으므로 rc=127 로 '없음'을 돌려준다 — 화면은 그대로 뜬다."""
import subprocess

SERVICES = ("api", "mock", "vision", "admin", "neis", "news", "rollup", "report")
RESTARTABLE = ("api", "mock", "vision")               # 관리 앱 자신(admin)은 재시작 목록에서 뺀다 — 자기 발을 쏘지 않게
JOBS = ("neis", "news", "rollup", "report")
UNITS = tuple(f"mealboard-{s}" for s in SERVICES)
LOG_UNITS = UNITS
MAX_LINES = 500

_SUDO = (
    *[("systemctl", "restart", "--no-block", f"mealboard-{s}.service") for s in RESTARTABLE],
    *[("systemctl", "start", "--no-block", f"mealboard-{j}.service") for j in JOBS],
    ("tailscale", "serve", "status", "--json"),
    ("tailscale", "funnel", "status", "--json"),
)
ALLOWED_SUDO = frozenset(_SUDO)


def sudo_lines(user):
    """deploy/sudoers-mealboard 의 본문 — 허용목록에서 그대로 만든다(둘이 어긋날 수 없게)"""
    cmds = [" ".join(("/usr/bin/" + a[0],) + a[1:]) for a in _SUDO]
    return [f"{user} ALL=(root) NOPASSWD: " + ", \\\n    ".join(cmds)]


def run(argv, sudo=False, timeout=20):
    """→ (rc, stdout, stderr). sudo 명령은 허용목록에 있어야 한다. 셸을 거치지 않는다"""
    argv = tuple(argv)
    if sudo:
        if argv not in ALLOWED_SUDO:
            raise PermissionError(f"허용목록에 없는 명령: {' '.join(argv)}")
        argv = ("sudo", "-n") + argv
    try:
        p = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"{argv[0]}: 이 기기에는 없다"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def restart(service):
    if service not in RESTARTABLE:
        raise PermissionError(f"재시작 대상이 아니다: {service}")
    return run(("systemctl", "restart", "--no-block", f"mealboard-{service}.service"), sudo=True)


def start_job(job):
    if job not in JOBS:
        raise PermissionError(f"작업이 아니다: {job}")
    return run(("systemctl", "start", "--no-block", f"mealboard-{job}.service"), sudo=True)


def unit_state(unit):
    """systemctl show 로 상태 한 줄. 없는 기기에서는 'unknown'"""
    rc, out, _ = run(("systemctl", "show", unit, "--property=ActiveState,SubState,ActiveEnterTimestamp,NRestarts,UnitFileState", "--no-pager"))
    if rc != 0:
        return {"unit": unit, "active": "unknown", "sub": None, "since": None, "restarts": None, "enabled": None}
    kv = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return {"unit": unit, "active": kv.get("ActiveState", "unknown"), "sub": kv.get("SubState"),
            "since": kv.get("ActiveEnterTimestamp") or None,
            "restarts": int(kv["NRestarts"]) if kv.get("NRestarts", "").isdigit() else None,
            "enabled": kv.get("UnitFileState") or None}          # disabled 인 카운팅 유닛은 재시작 대상이 아니다(mock↔vision Conflicts)


def journal(unit, lines=50):
    if unit not in LOG_UNITS:
        raise PermissionError(f"로그 대상이 아니다: {unit}")
    n = min(max(int(lines), 1), MAX_LINES)
    rc, out, err = run(("journalctl", "-u", unit, "-n", str(n), "--no-pager", "-o", "short-iso"))
    return rc, out if rc == 0 else err
