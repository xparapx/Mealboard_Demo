#!/usr/bin/env bash
# 통행로 송출용 라즈베리파이(42인치 모니터) 설정 — Pi 위에서 실행한다(멱등).
#
#   bash deploy/setup_kiosk_pi.sh [URL]          # 기본 URL https://kiosk.kjhs-meal.com
#
# 하는 일: 운영 PC 공개키 등록(deploy/kiosk_authorized_keys) · 데스크톱 자동 로그인 · 화면 꺼짐 금지 · Chromium 설치 ·
# 전원 인가 → 자동 로그인 → **systemd user 유닛 `mealboard-kiosk.service`(Restart=always)** 가 전체화면 키오스크로 송출 화면을 열고
# 죽으면 다시 띄운다(세션 시작 훅 = XDG autostart + labwc autostart, 유닛을 못 올리는 세션이면 직접 실행 폴백, 이중 실행은 flock) ·
# Wi‑Fi 절전 끄기 · Tailscale(원격 ssh 경로, WITH_TAILSCALE=0 으로 끔) · 시간표 전환(아침 등교 슬롯엔 교통 키오스크 URL, 급식 창엔 헤아림 — 화면 URL 전환 + HDMI‑CEC 입력 전환, 1분 타이머).
# 이 Pi 는 급식실 Pi(카운팅·API)와 별개다 — 코드·DB 없이 브라우저만 돈다(42인치 모니터 전용).
# 관리: systemctl --user status|restart mealboard-kiosk · journalctl --user -u mealboard-kiosk -n 50 · 기본 URL 은 ~/.config/mealboard-kiosk.url · 시간표·HDMI 는 ~/.config/mealboard-kiosk-sched.conf(SLOTS · MODE cec|blank|off) · 판정 확인 mealboard-kiosk-sched.sh dry
#
# sudo 가 필요한 단계(초기 1회, 사람 또는 NOPASSWD 등록 뒤 원격):
#   ① raspi-config 자동 로그인(B4)·화면 꺼짐 금지   ② apt install chromium(+정책 파일·폰트)   ③ nmcli 절전 설정   ④ tailscale 설치·up   ⑤ apt install v4l-utils wlr-randr(CEC — RPi OS 데스크톱엔 보통 이미 있음)
# 그 밖(스크립트·autostart 파일)은 전부 홈 디렉터리 안이라 sudo 없이 된다.
set -euo pipefail

URL="${1:-${KIOSK_URL:-https://kiosk.kjhs-meal.com}}"
HOME_DIR="${HOME}"
BIN="${HOME_DIR}/.local/bin"
AUTOSTART="${HOME_DIR}/.config/autostart"
RUNNER="${BIN}/mealboard-kiosk.sh"

say() { printf '\n== %s\n' "$*"; }

# sudo 단계(1·2·5·6·7의 apt)는 비밀번호를 칠 수 있는 터미널이거나 NOPASSWD 일 때만. `ssh kiosk bash -s < setup_kiosk_pi.sh` 처럼
# 파이프로 돌리면 사용자 영역(0·3·4 — 런너·유닛·훅)만 재적용된다(원격 갱신 경로, sudo 없음).
if sudo -n true 2>/dev/null || [ -t 1 ]; then SUDO_OK=1; else SUDO_OK=0; echo "   (sudo 불가 환경 — 1·2·5·6 단계와 7 의 apt 는 건너뛰고 사용자 영역만 적용)"; fi

say "0/7 운영 PC 공개키 등록 (deploy/kiosk_authorized_keys — 공개키만, sudo 없음)"
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

say "1/7 데스크톱 자동 로그인 · 화면 꺼짐 금지 (sudo)"
if [ "${SUDO_OK}" != 1 ]; then
  echo "   건너뜀(sudo 불가)"
elif command -v raspi-config >/dev/null; then
  sudo raspi-config nonint do_boot_behaviour B4      # B4 = Desktop, 자동 로그인
  sudo raspi-config nonint do_blanking 1             # 1 = 화면 꺼짐(blanking) 비활성
else
  echo "   raspi-config 없음 — 자동 로그인·화면 꺼짐은 수동 설정 필요"
fi

say "2/7 Chromium 설치 확인 (sudo)"
CHROMIUM="$(command -v chromium || command -v chromium-browser || true)"
if [ -z "${CHROMIUM}" ] && [ "${SUDO_OK}" != 1 ]; then
  echo "   Chromium 없음 + sudo 불가 — 터미널에서 다시 실행해 설치할 것"; exit 1
elif [ -z "${CHROMIUM}" ]; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq chromium || sudo apt-get install -y -qq chromium-browser
  CHROMIUM="$(command -v chromium || command -v chromium-browser)"
fi
echo "   ${CHROMIUM}"

say "2a/7 Chromium 관리 정책 — 번역 말풍선·비밀번호 저장 제안·기본 브라우저 안내 끄기 (sudo; 플래그 --disable-features=Translate 로는 안 꺼진다, 11-09 실측)"
if [ "${SUDO_OK}" = 1 ]; then
  sudo mkdir -p /etc/chromium/policies/managed
  printf '%s\n' '{' \
    '  "TranslateEnabled": false,' \
    '  "PasswordManagerEnabled": false,' \
    '  "DefaultBrowserSettingEnabled": false,' \
    '  "BrowserSignin": 0,' \
    '  "MetricsReportingEnabled": false,' \
    '  "AutofillAddressEnabled": false,' \
    '  "AutofillCreditCardEnabled": false' \
    '}' | sudo tee /etc/chromium/policies/managed/mealboard-kiosk.json >/dev/null
  echo "   /etc/chromium/policies/managed/mealboard-kiosk.json"
else
  echo "   건너뜀(sudo 불가) — 번역 말풍선이 뜨면 터미널에서 다시 실행"
fi

say "2b/7 한글 폰트 (없으면 화면의 한글이 전부 네모 — 11-09 실측: Raspberry Pi OS 기본엔 한글 폰트가 없다)"
if [ "$(fc-list :lang=ko 2>/dev/null | wc -l)" -gt 0 ]; then
  echo "   있음: $(fc-match 'sans-serif:lang=ko')"
elif [ "${SUDO_OK}" = 1 ]; then
  sudo apt-get install -y -qq fonts-noto-cjk && echo "   fonts-noto-cjk 설치"
else
  # sudo 없이: 사용자 폰트 폴더에 Noto Sans KR(가변, OFL) 한 파일 — CSS 폴백 목록(Pretendard → Noto Sans KR → sans-serif)에 바로 맞는다.
  FONT_DIR="${HOME_DIR}/.local/share/fonts"; mkdir -p "${FONT_DIR}"
  curl -fsSL --max-time 120 -o "${FONT_DIR}/NotoSansKR[wght].ttf" "https://github.com/google/fonts/raw/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf" \
    && fc-cache -f >/dev/null && echo "   사용자 폰트 설치: $(fc-match 'sans-serif:lang=ko')" \
    || echo "   폰트 내려받기 실패 — 터미널에서 sudo apt install fonts-noto-cjk"
fi

say "3/7 감시 루프 스크립트 ${RUNNER}"
mkdir -p "${BIN}" "${AUTOSTART}"
cat > "${RUNNER}" <<'EOF'
#!/usr/bin/env bash
# 송출 화면을 전체화면 키오스크로 열고, 브라우저가 죽으면 5초 뒤 다시 연다.
# URL 은 ~/.config/mealboard-kiosk.url 한 줄(기본). 시간표 스크립트(7/7)가 ~/.config/mealboard-kiosk.current 에 지금 보일 URL 을 적어 두면 그쪽이 우선.
URL_FILE="${HOME}/.config/mealboard-kiosk.url"; CUR_FILE="${HOME}/.config/mealboard-kiosk.current"
URL="https://kiosk.kjhs-meal.com"
[ -r "${URL_FILE}" ] && URL="$(head -n1 "${URL_FILE}")"
[ -s "${CUR_FILE}" ] && URL="$(head -n1 "${CUR_FILE}")"
CHROMIUM="$(command -v chromium || command -v chromium-browser)"
PROFILE="${HOME}/.config/mealboard-kiosk-profile"

# 표시 플랫폼: Wayland 세션이면 명시(hint=auto 는 XDG_SESSION_TYPE 이 없으면 X11 로 가서 죽는다 — 11-09 실측), 아니면 Xwayland :0.
if [ -n "${WAYLAND_DISPLAY:-}" ]; then PLATFORM="--ozone-platform=wayland"; else PLATFORM="--ozone-platform=x11"; export DISPLAY="${DISPLAY:-:0}"; fi

# 한 세션에 하나만(systemd 유닛과 autostart 폴백이 겹쳐도 두 번째는 조용히 끝난다).
exec 9>"${HOME}/.config/mealboard-kiosk.lock"
flock -n 9 || exit 0

# 망이 붙을 때까지 기다린다(부팅 직후 Wi‑Fi 가 늦을 수 있다). 최대 2분, 그 뒤엔 그냥 연다 — 화면이 자체 재시도한다.
# 학교 망은 Cloudflare 엣지 IP 하나(104.21.70.130)를 막는다(09-18·11-10 실측) — A 레코드를 하나씩 시도해야 '망 없음' 과 가른다.
reach() {
  local host port ip; host="${1#*://}"; host="${host%%/*}"; case "$1" in https://*) port=443 ;; *) port=80 ;; esac
  for ip in $(getent ahostsv4 "${host}" 2>/dev/null | awk '{print $1}' | sort -u); do
    curl -4 -fsS --connect-timeout 4 --max-time 8 --resolve "${host}:${port}:${ip}" -o /dev/null "$1" 2>/dev/null && return 0
  done
  return 1
}
for _ in $(seq 1 24); do
  reach "${URL}" && break
  sleep 5
done

while true; do
  "${CHROMIUM}" \
    --kiosk --start-fullscreen --noerrdialogs --disable-infobars --no-first-run \
    --disable-session-crashed-bubble --disable-features=Translate,TranslateUI --lang=ko-KR \
    --check-for-update-interval=31536000 --autoplay-policy=no-user-gesture-required \
    --password-store=basic "${PLATFORM}" --user-data-dir="${PROFILE}" \
    "${URL}" || true
  # --password-store=basic: 없으면 Chromium 이 GNOME 키링 '새 키링 비밀번호' 대화상자를 띄우고 그 뒤에서 흰 화면으로 멈춘다(11-09 실측).
  sleep 5
done
EOF
chmod +x "${RUNNER}"
printf '%s\n' "${URL}" > "${HOME_DIR}/.config/mealboard-kiosk.url"

say "4/7 systemd user 유닛 mealboard-kiosk.service + 세션 시작 훅 (전원 인가 → 자동 로그인 → 유닛 기동)"
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

say "5/7 Wi‑Fi 절전 끄기 (2.4G 끊김 방지, sudo)"
CON="$(nmcli -t -f NAME,TYPE con show --active 2>/dev/null | awk -F: '$2 ~ /wireless/ {print $1; exit}')"
if [ -n "${CON}" ]; then
  # 데스크톱 사용자는 netdev 그룹이라 보통 sudo 없이 된다(polkit); 안 되면 sudo.
  if nmcli con modify "${CON}" wifi.powersave 2 2>/dev/null || { [ "${SUDO_OK}" = 1 ] && sudo nmcli con modify "${CON}" wifi.powersave 2; }; then
    echo "   ${CON}: powersave=disable"
  else
    echo "   ${CON}: 절전 설정 실패(권한) — 터미널에서 다시 실행"
  fi
else
  echo "   활성 Wi‑Fi 연결 없음 — 건너뜀"
fi

say "6/7 Tailscale (학교 Wi‑Fi 는 클라이언트 격리라 LAN 접속이 막힌다 — tailnet 으로 ssh, sudo)"
if [ "${WITH_TAILSCALE:-1}" = "1" ] && [ "${SUDO_OK}" != 1 ] && ! tailscale status >/dev/null 2>&1; then
  echo "   건너뜀(sudo 불가) — 터미널에서 다시 실행"
elif [ "${WITH_TAILSCALE:-1}" = "1" ]; then
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

say "7/7 시간표 전환 — 아침 등교(교통 키오스크) · 급식 창(헤아림) 화면 + HDMI 입력 (1분 타이머)"
# 한 대의 42인치로 아침 등교 시간엔 교통 키오스크(https://tr-kiosk.kjhs-lab.com/), 급식 시간엔 헤아림 송출을 보여 주고(11-10 사용자 요청),
# 그 밖엔 TV 를 다른 입력으로 돌려준다(11-09). 판정 두 갈래:
#   · 급식 창  = 송출 주소의 /api/status feed.now(급식 창 안에서만 값, 급식 없는 날·창 밖은 null) — 시간표·휴일 규칙을 여기에 복제하지 않는다.
#   · 시간표 슬롯 = conf 의 SLOTS("시작-끝 URL [요일]", 로컬 시계) — 급식 없는 날(feed.meal_day=false, 휴일·방학)은 슬롯도 쉰다.
# 화면 URL 은 ~/.config/mealboard-kiosk.current 에 적고, 바뀐 순간에만 mealboard-kiosk 유닛을 재시작한다(런너가 그 파일을 읽는다 — 전환 때 5초쯤 검은 화면).
# HDMI 는 MODE 로: cec(기본) TV 에 '나를 보여라'(Image View On+Active Source) / '끝났다'(Inactive Source, OTHER 가 있으면 그 입력으로 Set Stream Path);
#   TV 가 CEC 를 모르면 아무 일도 안 일어난다(켜 둬도 해롭지 않다). blank = 자동 전환 HDMI 스위치용(창 밖엔 Pi 출력 자체를 끔). off = HDMI 안 건드림(화면 전환만).
# 전이에만 명령(매분 쏘지 않는다 — 사람이 리모컨으로 돌려 둔 것과 싸우지 않게). 첫 실행은 상태만 기록. 망 단절 시 급식 판정은 유지, 슬롯은 로컬 시계라 계속 동작.
if [ "${SUDO_OK}" = 1 ]; then
  command -v cec-ctl >/dev/null || sudo apt-get install -y -qq v4l-utils
  command -v wlr-randr >/dev/null || sudo apt-get install -y -qq wlr-randr
fi
command -v cec-ctl >/dev/null || echo "   cec-ctl 없음(v4l-utils) — sudo 가능한 터미널에서 다시 실행하면 설치된다. 그때까지 CEC 전환은 건너뛴다"
SCHED_SH="${BIN}/mealboard-kiosk-sched.sh"
SCHED_CONF="${HOME_DIR}/.config/mealboard-kiosk-sched.conf"
# 11-09 의 옛 이름(mealboard-kiosk-hdmi.*) 정리 — 설정·상태는 새 이름으로 승계
systemctl --user disable --now mealboard-kiosk-hdmi.timer 2>/dev/null || true
rm -f "${UNIT_DIR}/mealboard-kiosk-hdmi.service" "${UNIT_DIR}/mealboard-kiosk-hdmi.timer" "${BIN}/mealboard-kiosk-hdmi.sh"
OLD_CONF="${HOME_DIR}/.config/mealboard-kiosk-hdmi.conf"; OLD_STATE="${HOME_DIR}/.config/mealboard-kiosk-hdmi.state"
[ -f "${OLD_STATE}" ] && [ ! -f "${HOME_DIR}/.config/mealboard-kiosk-sched.state" ] && mv "${OLD_STATE}" "${HOME_DIR}/.config/mealboard-kiosk-sched.state"
cat > "${SCHED_SH}" <<'EOF'
#!/usr/bin/env bash
# 시간표 전환(setup_kiosk_pi.sh 7/7 이 설치). 1분 타이머가 인자 없이 부른다.
#   시험: mealboard-kiosk-sched.sh dry      판정만 출력(아무것도 안 바꿈)
#         mealboard-kiosk-sched.sh on|off   HDMI 만 강제(TV 반응 확인용)
set -u
CONF="${HOME}/.config/mealboard-kiosk-sched.conf"; STATE="${HOME}/.config/mealboard-kiosk-sched.state"
CUR="${HOME}/.config/mealboard-kiosk.current"
MODE=cec; OTHER=""; SLOTS=""
[ -r "${CONF}" ] && . "${CONF}"
DEFAULT_URL="$(head -n1 "${HOME}/.config/mealboard-kiosk.url" 2>/dev/null || echo https://kiosk.kjhs-meal.com)"
ORIGIN="$(printf '%s' "${DEFAULT_URL}" | sed -E 's#^(https?://[^/]+).*#\1#')"
log() { logger -t mealboard-kiosk-sched -- "$*" 2>/dev/null; echo "$*"; }
arg="${1:-}"

# ① 급식 판정(API) — meal: on|off|unknown, meal_day: yes|no|unknown
meal=unknown; meal_day=unknown
fetch_status() {   # 학교 망이 Cloudflare 엣지 IP 하나를 막는다(09-18·11-10 실측) — A 레코드를 하나씩 시도
  local host port ip; host="${ORIGIN#*://}"; case "${ORIGIN}" in https://*) port=443 ;; *) port=80 ;; esac
  for ip in $(getent ahostsv4 "${host}" 2>/dev/null | awk '{print $1}' | sort -u); do
    curl -4 -fsS --connect-timeout 4 --max-time 8 --resolve "${host}:${port}:${ip}" "${ORIGIN}/api/status" 2>/dev/null && return 0
  done
  return 1
}
if body="$(fetch_status)"; then
  read -r meal meal_day < <(printf '%s' "${body}" | python3 -c 'import sys,json
f=(json.load(sys.stdin).get("feed") or {}); print("on" if f.get("now") else "off", "yes" if f.get("meal_day", True) else "no")' 2>/dev/null) || { meal=unknown; meal_day=unknown; }
fi

# ② 시간표 슬롯(로컬 시계) — SLOTS 한 줄: "HH:MM-HH:MM URL [요일 1~7, 기본 12345=월~금]". 급식 없는 날은 슬롯도 쉰다(휴일·방학).
slot_url=""; now_hm="$(date +%H:%M)"; dow="$(date +%u)"
while read -r range url days; do
  [ -z "${range}" ] && continue; case "${range}" in \#*) continue ;; esac
  days="${days:-12345}"; case "${days}" in *"${dow}"*) ;; *) continue ;; esac
  s="${range%-*}"; e="${range#*-}"
  if [[ "${now_hm}" > "${s}" || "${now_hm}" == "${s}" ]] && [[ "${now_hm}" < "${e}" ]]; then slot_url="${url}"; break; fi
done <<< "${SLOTS}"
[ "${meal_day}" = no ] && slot_url=""

# ③ 원하는 화면(url)·TV 전원(want: on|off|keep)
if   [ -n "${slot_url}" ]; then want=on;   url="${slot_url}"
elif [ "${meal}" = on ];    then want=on;   url="${DEFAULT_URL}"
elif [ "${meal}" = off ];   then want=off;  url="${DEFAULT_URL}"
else                             want=keep; url="${DEFAULT_URL}"; fi      # API 실패 — HDMI 는 유지, 화면은 기본
have="$(cat "${STATE}" 2>/dev/null || true)"
cur="$(cat "${CUR}" 2>/dev/null || echo "${DEFAULT_URL}")"
if [ "${arg}" = dry ]; then
  echo "now=${now_hm} dow=${dow} meal=${meal} meal_day=${meal_day} slot=${slot_url:--} → url=${url} hdmi=${want} (지금 화면=${cur} hdmi 상태=${have:--})"; exit 0
fi

# ④ 화면 전환 — URL 이 바뀐 순간에만 유닛 재시작(런너가 .current 를 읽는다)
if [ "${url}" != "${cur}" ]; then
  printf '%s\n' "${url}" > "${CUR}"
  systemctl --user restart mealboard-kiosk 2>/dev/null && log "화면 전환 → ${url}" || log "화면 전환 실패(유닛 재시작 불가) → ${url}"
fi

# ⑤ HDMI — 강제(on|off)가 아니면 전이에만. 첫 실행은 상태 기록만.
case "${arg}" in on|off) want="${arg}" ;; esac
[ "${MODE}" = off ] && exit 0
if [ -z "${arg}" ]; then
  [ "${want}" = keep ] && exit 0
  if [ -z "${have}" ]; then printf '%s\n' "${want}" > "${STATE}"; log "초기 HDMI 상태 기록 ${want} (명령 없음)"; exit 0; fi
  [ "${want}" = "${have}" ] && exit 0
fi

# CEC 어댑터 = 두 HDMI 중 물리 주소가 잡힌 쪽(모니터가 꽂힌 포트). 출력: "<dev> <phys>"
cec_dev() {
  local d pa
  for d in /dev/cec0 /dev/cec1; do
    [ -e "${d}" ] || continue
    pa="$(cec-ctl -d "${d}" 2>/dev/null | sed -n 's/.*Physical Address *: *\([0-9a-f.]*\).*/\1/p' | head -1)"
    case "${pa}" in ""|f.f.f.f) ;; *) echo "${d} ${pa}"; return 0 ;; esac
  done
  return 1
}
cec_send() {        # $1 on|off — Image View On·Inactive Source 는 TV(0)에게, Active Source·Set Stream Path 는 방송(15)
  local act="$1" dev pa
  command -v cec-ctl >/dev/null || { log "cec-ctl 없음 — CEC 건너뜀"; return 0; }
  read -r dev pa < <(cec_dev) || { log "CEC 물리 주소 없음(모니터 미연결 또는 CEC 없는 모니터) — 건너뜀"; return 0; }
  cec-ctl -d "${dev}" --playback --osd-name Hearim >/dev/null 2>&1 || true   # 재생기기로 등록(멱등)
  if [ "${act}" = on ]; then
    cec-ctl -d "${dev}" --to 0 --image-view-on >/dev/null 2>&1
    sleep 1
    cec-ctl -d "${dev}" --to 15 --active-source phys-addr="${pa}" >/dev/null 2>&1
  else
    cec-ctl -d "${dev}" --to 0 --inactive-source phys-addr="${pa}" >/dev/null 2>&1
    [ -n "${OTHER}" ] && cec-ctl -d "${dev}" --to 15 --set-stream-path phys-addr="${OTHER}" >/dev/null 2>&1
  fi
  log "CEC ${act} (${dev} ${pa}${OTHER:+ → ${OTHER}})"
}
hdmi_out() {        # $1 on|off — Pi 의 HDMI 출력(blank 모드, 자동 전환 스위치가 신호 유무로 고른다)
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
  local out; out="$(wlr-randr 2>/dev/null | awk 'NR==1{print $1}')"
  [ -n "${out}" ] || { log "wlr-randr 출력 없음 — 건너뜀"; return 0; }
  wlr-randr --output "${out}" "--$1" >/dev/null 2>&1 && log "HDMI 출력 $1 (${out})"
}

if [ "${want}" = on ]; then
  [ "${MODE}" = blank ] && hdmi_out on
  cec_send on
else
  cec_send off
  [ "${MODE}" = blank ] && hdmi_out off
fi
printf '%s\n' "${want}" > "${STATE}"
EOF
chmod +x "${SCHED_SH}"
if [ ! -f "${SCHED_CONF}" ]; then
  OLD_MODE=cec; OLD_OTHER=""
  if [ -r "${OLD_CONF}" ]; then OLD_MODE="$(sed -n 's/^MODE=//p' "${OLD_CONF}" | tail -1)"; OLD_OTHER="$(sed -n 's/^OTHER=//p' "${OLD_CONF}" | tail -1)"; OLD_MODE="${OLD_MODE:-cec}"; fi
  cat > "${SCHED_CONF}" <<EOF
# 시간표 전환 설정 — ~/.local/bin/mealboard-kiosk-sched.sh 가 읽는다(1분 타이머 mealboard-kiosk-sched.timer). 판정 확인: mealboard-kiosk-sched.sh dry
# MODE: cec(기본, TV 가 CEC 를 알면 급식·등교 시간에만 이 Pi 를 보여 준다) | blank(자동 전환 HDMI 스위치용, 그 밖엔 Pi 출력 끔) | off(HDMI 안 건드림, 화면 전환만)
MODE=${OLD_MODE}
# OTHER: 그 밖의 시간에 보여 줄 TV 입력의 CEC 물리 주소(예: 2.0.0.0 = HDMI 2). 비우면 TV 가 '이전 입력' 으로 돌아가는 데 맡긴다
OTHER=${OLD_OTHER}
# SLOTS: 한 줄에 하나 — "시작-끝 URL [요일 1~7, 기본 12345=월~금]". 이 시간엔 그 URL 을 띄우고 TV 를 이 Pi 로. 급식 없는 날(휴일·방학)은 슬롯도 쉰다.
# 급식 시간은 적지 않는다 — 송출 주소의 /api/status 가 급식 창·급식 있는 날을 알려 준다.
SLOTS="
07:30-08:30 https://tr-kiosk.kjhs-lab.com/
"
EOF
fi
rm -f "${OLD_CONF}"
cat > "${UNIT_DIR}/mealboard-kiosk-sched.service" <<EOF
[Unit]
Description=Hearim kiosk schedule (screen URL + HDMI input by time of day)

[Service]
Type=oneshot
ExecStart=${SCHED_SH}
EOF
cat > "${UNIT_DIR}/mealboard-kiosk-sched.timer" <<'EOF'
[Unit]
Description=Hearim kiosk schedule — every minute

[Timer]
OnBootSec=90s
OnUnitActiveSec=60s
AccuracySec=10s

[Install]
WantedBy=timers.target
EOF
systemctl --user daemon-reload 2>/dev/null || true
systemctl --user enable --now mealboard-kiosk-sched.timer 2>/dev/null || echo "   (user systemd 에 아직 못 붙음 — 다음 로그인부터 타이머가 돈다)"
echo "   스크립트 ${SCHED_SH} · 설정 ${SCHED_CONF} · 지금 화면 ~/.config/mealboard-kiosk.current · HDMI 상태 ~/.config/mealboard-kiosk-sched.state"
echo "   판정 확인: ${SCHED_SH} dry   HDMI 시험: ${SCHED_SH} on|off   로그: journalctl --user -t mealboard-kiosk-sched -n 20   CEC 점검: cec-ctl -d /dev/cec0 --playback -S"

say "완료 — 전원을 넣으면 자동 로그인 뒤 systemd 유닛이 ${URL} 을 전체화면으로 띄운다 (지금 적용: sudo reboot)"
echo "   상태: systemctl --user status mealboard-kiosk   재시작: systemctl --user restart mealboard-kiosk   로그: journalctl --user -u mealboard-kiosk -n 50"
echo "   URL 변경: ~/.config/mealboard-kiosk.url 수정 뒤 restart.  브라우저 확인: pgrep -af chromium | head -1"
echo "   시간표: 아침 슬롯·급식 창에 TV 가 이 Pi 로 안 넘어오면 TV 메뉴의 CEC 를 켠다. CEC 없는 모니터·스위치 사용이면 sched.conf 의 MODE=blank. 슬롯 추가는 SLOTS 한 줄"
