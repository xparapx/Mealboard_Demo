#!/usr/bin/env bash
# 통행로 송출용 라즈베리파이(42인치 모니터) 설정 — Pi 위에서 실행한다(멱등).
#
#   bash deploy/setup_kiosk_pi.sh [URL]          # 기본 URL https://kiosk.kjhs-meal.com
#
# 하는 일: 데스크톱 자동 로그인 · 화면 꺼짐 금지 · Chromium 설치 · 로그인 직후 전체화면 키오스크로
# 송출 화면을 열고 꺼지면 다시 여는 감시 루프(XDG autostart) · Wi‑Fi 절전 끄기.
# 이 Pi 는 급식실 Pi(카운팅·API)와 별개다 — 코드·DB 없이 브라우저만 돈다.
#
# sudo 가 필요한 단계(초기 1회, 사람 또는 NOPASSWD 등록 뒤 원격):
#   ① raspi-config 자동 로그인(B4)·화면 꺼짐 금지   ② apt install chromium   ③ nmcli 절전 설정
# 그 밖(스크립트·autostart 파일)은 전부 홈 디렉터리 안이라 sudo 없이 된다.
set -euo pipefail

URL="${1:-${KIOSK_URL:-https://kiosk.kjhs-meal.com}}"
HOME_DIR="${HOME}"
BIN="${HOME_DIR}/.local/bin"
AUTOSTART="${HOME_DIR}/.config/autostart"
RUNNER="${BIN}/mealboard-kiosk.sh"

say() { printf '\n== %s\n' "$*"; }

say "1/5 데스크톱 자동 로그인 · 화면 꺼짐 금지 (sudo)"
if command -v raspi-config >/dev/null; then
  sudo raspi-config nonint do_boot_behaviour B4      # B4 = Desktop, 자동 로그인
  sudo raspi-config nonint do_blanking 1             # 1 = 화면 꺼짐(blanking) 비활성
else
  echo "   raspi-config 없음 — 자동 로그인·화면 꺼짐은 수동 설정 필요"
fi

say "2/5 Chromium 설치 확인 (sudo)"
CHROMIUM="$(command -v chromium || command -v chromium-browser || true)"
if [ -z "${CHROMIUM}" ]; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq chromium || sudo apt-get install -y -qq chromium-browser
  CHROMIUM="$(command -v chromium || command -v chromium-browser)"
fi
echo "   ${CHROMIUM}"

say "3/5 감시 루프 스크립트 ${RUNNER}"
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

say "4/5 로그인 시 자동 실행 (XDG autostart — wayfire·labwc·X11 공통)"
cat > "${AUTOSTART}/mealboard-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Mealboard kiosk
Comment=헤아림 통행로 송출 화면
Exec=${RUNNER}
X-GNOME-Autostart-enabled=true
EOF

say "5/5 Wi‑Fi 절전 끄기 (2.4G 끊김 방지, sudo)"
CON="$(nmcli -t -f NAME,TYPE con show --active 2>/dev/null | awk -F: '$2 ~ /wireless/ {print $1; exit}')"
if [ -n "${CON}" ]; then
  sudo nmcli con modify "${CON}" wifi.powersave 2 && echo "   ${CON}: powersave=disable"
else
  echo "   활성 Wi‑Fi 연결 없음 — 건너뜀"
fi

say "완료 — 재부팅하면 자동 로그인 뒤 ${URL} 이 전체화면으로 뜬다 (sudo reboot)"
echo "   URL 변경: ~/.config/mealboard-kiosk.url 수정 뒤 재로그인.  확인: pgrep -af chromium | head -1"
