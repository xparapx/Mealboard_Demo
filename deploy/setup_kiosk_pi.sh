#!/usr/bin/env bash
# 통행로 송출용 라즈베리파이(42인치 모니터) 설정 — Pi 위에서 실행한다(멱등).
#
#   bash deploy/setup_kiosk_pi.sh [URL]          # 기본 URL https://kiosk.kjhs-meal.com
#
# 하는 일: 운영 PC 공개키 등록(deploy/kiosk_authorized_keys) · 데스크톱 자동 로그인 · 화면 꺼짐 금지 · Chromium 설치 ·
# 전원 인가 → 자동 로그인 → **systemd user 유닛 `mealboard-kiosk.service`(Restart=always)** 가 전체화면 키오스크로 송출 화면을 열고
# 죽으면 다시 띄운다(세션 시작 훅 = XDG autostart + labwc autostart, 유닛을 못 올리는 세션이면 직접 실행 폴백, 이중 실행은 flock) ·
# Wi‑Fi 절전 끄기 · Tailscale(원격 ssh 경로, WITH_TAILSCALE=0 으로 끔).
# 이 Pi 는 급식실 Pi(카운팅·API)와 별개다 — 코드·DB 없이 브라우저만 돈다(42인치 모니터 전용).
# 관리: systemctl --user status|restart mealboard-kiosk · journalctl --user -u mealboard-kiosk -n 50 · URL 은 ~/.config/mealboard-kiosk.url
#
# sudo 가 필요한 단계(초기 1회, 사람 또는 NOPASSWD 등록 뒤 원격):
#   ① raspi-config 자동 로그인(B4)·화면 꺼짐 금지   ② apt install chromium   ③ nmcli 절전 설정   ④ tailscale 설치·up
# 그 밖(스크립트·autostart 파일)은 전부 홈 디렉터리 안이라 sudo 없이 된다.
set -euo pipefail

URL="${1:-${KIOSK_URL:-https://kiosk.kjhs-meal.com}}"
HOME_DIR="${HOME}"
BIN="${HOME_DIR}/.local/bin"
AUTOSTART="${HOME_DIR}/.config/autostart"
RUNNER="${BIN}/mealboard-kiosk.sh"

say() { printf '\n== %s\n' "$*"; }

say "0/6 운영 PC 공개키 등록 (deploy/kiosk_authorized_keys — 공개키만, sudo 없음)"
KEYS_URL="https://raw.githubusercontent.com/xparapx/Mealboard_Demo/main/deploy/kiosk_authorized_keys"
mkdir -p "${HOME_DIR}/.ssh" && chmod 700 "${HOME_DIR}/.ssh"
touch "${HOME_DIR}/.ssh/authorized_keys" && chmod 600 "${HOME_DIR}/.ssh/authorized_keys"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-/dev/null}")" 2>/dev/null && pwd || true)"
if [ -n "${HERE}" ] && [ -r "${HERE}/kiosk_authorized_keys" ]; then
  KEYS="$(cat "${HERE}/kiosk_authorized_keys")"
else
  KEYS="$(curl -fsSL --max-time 15 "${KEYS_URL}")"
fi
ADDED=0
while IFS= read -r k; do
  case "${k}" in ssh-ed25519\ *|ssh-rsa\ *|ecdsa-*) ;; *) continue ;; esac
  grep -qxF "${k}" "${HOME_DIR}/.ssh/authorized_keys" || { printf '%s\n' "${k}" >> "${HOME_DIR}/.ssh/authorized_keys"; ADDED=$((ADDED+1)); }
done <<< "${KEYS}"
echo "   추가 ${ADDED}개 · 전체 $(grep -c . "${HOME_DIR}/.ssh/authorized_keys")개"

say "1/6 데스크톱 자동 로그인 · 화면 꺼짐 금지 (sudo)"
if command -v raspi-config >/dev/null; then
  sudo raspi-config nonint do_boot_behaviour B4      # B4 = Desktop, 자동 로그인
  sudo raspi-config nonint do_blanking 1             # 1 = 화면 꺼짐(blanking) 비활성
else
  echo "   raspi-config 없음 — 자동 로그인·화면 꺼짐은 수동 설정 필요"
fi

say "2/6 Chromium 설치 확인 (sudo)"
CHROMIUM="$(command -v chromium || command -v chromium-browser || true)"
if [ -z "${CHROMIUM}" ]; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq chromium || sudo apt-get install -y -qq chromium-browser
  CHROMIUM="$(command -v chromium || command -v chromium-browser)"
fi
echo "   ${CHROMIUM}"

say "3/6 감시 루프 스크립트 ${RUNNER}"
mkdir -p "${BIN}" "${AUTOSTART}"
cat > "${RUNNER}" <<'EOF'
#!/usr/bin/env bash
# 송출 화면을 전체화면 키오스크로 열고, 브라우저가 죽으면 5초 뒤 다시 연다.
# URL 은 ~/.config/mealboard-kiosk.url 한 줄(없으면 기본값).
URL_FILE="${HOME}/.config/mealboard-kiosk.url"
URL="https://kiosk.kjhs-meal.com"
[ -r "${URL_FILE}" ] && URL="$(head -n1 "${URL_FILE}")"
CHROMIUM="$(command -v chromium || command -v chromium-browser)"
PROFILE="${HOME}/.config/mealboard-kiosk-profile"

# 한 세션에 하나만(systemd 유닛과 autostart 폴백이 겹쳐도 두 번째는 조용히 끝난다).
exec 9>"${HOME}/.config/mealboard-kiosk.lock"
flock -n 9 || exit 0

# 망이 붙을 때까지 기다린다(부팅 직후 Wi‑Fi 가 늦을 수 있다). 최대 2분, 그 뒤엔 그냥 연다 — 화면이 자체 재시도한다.
for _ in $(seq 1 24); do
  curl -fsS --max-time 4 -o /dev/null "${URL}" && break
  sleep 5
done

while true; do
  "${CHROMIUM}" \
    --kiosk --start-fullscreen --noerrdialogs --disable-infobars --no-first-run \
    --disable-session-crashed-bubble --disable-features=TranslateUI \
    --check-for-update-interval=31536000 --autoplay-policy=no-user-gesture-required \
    --ozone-platform-hint=auto --user-data-dir="${PROFILE}" \
    "${URL}" || true
  sleep 5
done
EOF
chmod +x "${RUNNER}"
printf '%s\n' "${URL}" > "${HOME_DIR}/.config/mealboard-kiosk.url"

say "4/6 systemd user 유닛 mealboard-kiosk.service + 세션 시작 훅 (전원 인가 → 자동 로그인 → 유닛 기동)"
UNIT_DIR="${HOME_DIR}/.config/systemd/user"
LAUNCH="${BIN}/mealboard-kiosk-launch.sh"
mkdir -p "${UNIT_DIR}"
cat > "${UNIT_DIR}/mealboard-kiosk.service" <<EOF
[Unit]
Description=Hearim kiosk (Chromium fullscreen, ${URL})
# 그래픽 세션(WAYLAND_DISPLAY) 안에서만 뜻이 있다 — 세션 시작 훅(launch.sh)이 환경을 넘겨 주고 start 한다.
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
ExecStart=${RUNNER}
Restart=always
RestartSec=5
# 브라우저가 죽어도 유닛이 5초 뒤 다시 올린다(런너 안의 루프와 겹쳐도 flock 이 한 개만 남긴다).

[Install]
WantedBy=graphical-session.target
EOF
systemctl --user daemon-reload 2>/dev/null || true
systemctl --user enable mealboard-kiosk.service 2>/dev/null || echo "   (user systemd 에 아직 못 붙음 — 로그인 세션에서 훅이 start 한다)"

# 세션 시작 훅: 데스크톱 환경(WAYLAND_DISPLAY 등)을 user systemd 로 넘기고 유닛을 켠다. 유닛을 못 올리는 세션이면 직접 실행.
cat > "${LAUNCH}" <<EOF
#!/usr/bin/env bash
systemctl --user import-environment WAYLAND_DISPLAY DISPLAY XDG_RUNTIME_DIR XDG_SESSION_TYPE XAUTHORITY 2>/dev/null || true
systemctl --user start mealboard-kiosk.service 2>/dev/null || exec "${RUNNER}"
EOF
chmod +x "${LAUNCH}"

# 훅 ① XDG autostart(lxsession-xdg-autostart·X11·wayfire) ② labwc autostart(Raspberry Pi OS Bookworm/Trixie 기본 세션) — 둘이 겹쳐도 start 는 멱등.
cat > "${AUTOSTART}/mealboard-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Mealboard kiosk
Comment=헤아림 통행로 송출 화면
Exec=${LAUNCH}
X-GNOME-Autostart-enabled=true
EOF
LABWC="${HOME_DIR}/.config/labwc/autostart"
mkdir -p "$(dirname "${LABWC}")"
touch "${LABWC}"
grep -qF "${LAUNCH}" "${LABWC}" || printf '%s &\n' "${LAUNCH}" >> "${LABWC}"
echo "   유닛 ${UNIT_DIR}/mealboard-kiosk.service · 훅 ${AUTOSTART}/mealboard-kiosk.desktop, ${LABWC}"

say "5/6 Wi‑Fi 절전 끄기 (2.4G 끊김 방지, sudo)"
CON="$(nmcli -t -f NAME,TYPE con show --active 2>/dev/null | awk -F: '$2 ~ /wireless/ {print $1; exit}')"
if [ -n "${CON}" ]; then
  sudo nmcli con modify "${CON}" wifi.powersave 2 && echo "   ${CON}: powersave=disable"
else
  echo "   활성 Wi‑Fi 연결 없음 — 건너뜀"
fi

say "6/6 Tailscale (학교 Wi‑Fi 는 클라이언트 격리라 LAN 접속이 막힌다 — tailnet 으로 ssh, sudo)"
if [ "${WITH_TAILSCALE:-1}" = "1" ]; then
  if ! command -v tailscale >/dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
  fi
  if ! tailscale status >/dev/null 2>&1; then
    echo "   아래에 로그인 주소가 나오면 휴대폰·PC 브라우저로 열어 tailnet 계정으로 승인한다(최대 5분 대기)."
    echo "   학교 망이 Tailscale 제어 서버를 막으면 여기서 멈춘다 → 휴대폰 핫스팟으로 잠시 옮겨 다시 실행."
    sudo tailscale up --hostname kiosk --timeout 300s || echo "   tailscale up 미완료 — 나중에 'sudo tailscale up --hostname kiosk' 재실행"
  fi
  tailscale ip -4 2>/dev/null | sed 's/^/   tailnet IP /' || true
else
  echo "   WITH_TAILSCALE=0 — 건너뜀"
fi

say "완료 — 전원을 넣으면 자동 로그인 뒤 systemd 유닛이 ${URL} 을 전체화면으로 띄운다 (지금 적용: sudo reboot)"
echo "   상태: systemctl --user status mealboard-kiosk   재시작: systemctl --user restart mealboard-kiosk   로그: journalctl --user -u mealboard-kiosk -n 50"
echo "   URL 변경: ~/.config/mealboard-kiosk.url 수정 뒤 restart.  브라우저 확인: pgrep -af chromium | head -1"
