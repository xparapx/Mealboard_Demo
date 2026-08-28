#!/usr/bin/env bash
# Pi 에서 최초 1회 (그리고 유닛/의존성이 바뀔 때마다) 실행. 몇 번 실행해도 안전하게 설계.
set -euo pipefail
APP=/opt/mealboard
REPO=https://github.com/xparapx/Mealboard_Demo.git

echo "== 1. 시스템"
sudo timedatectl set-timezone Asia/Seoul
sudo apt update
sudo apt install -y git python3-picamera2 sqlite3 curl
getent group mealboard >/dev/null || sudo groupadd mealboard
sudo usermod -aG mealboard "$USER"

echo "== 2. uv"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "== 3. 코드 (팀 공용 체크아웃)"
sudo mkdir -p "$APP"
sudo chown "$USER":mealboard "$APP"
sudo chmod 2775 "$APP"                    # setgid: 이후 생기는 파일도 그룹 소유
[ -d "$APP/.git" ] || git clone "$REPO" "$APP"
cd "$APP"

echo "== 4. venv — 반드시 이 순서 (picamera2 는 시스템 것을 빌려 씀)"
[ -d .venv ] || uv venv --system-site-packages
uv sync

echo "== 5. 설정"
[ -f .env ] || { cp .env.example .env; echo ">> $APP/.env 값을 채우세요 (NEIS_KEY 등)"; }
mkdir -p data static/icons

echo "== 6. systemd 유닛 (저장소 deploy/ → /etc/systemd/system/)"
for u in deploy/*.service deploy/*.timer; do
  [ -f "$u" ] || continue
  tmp=$(mktemp)
  sed "s/__USER__/$USER/g" "$u" > "$tmp"
  sudo install -m 644 -C -v "$tmp" "/etc/systemd/system/$(basename "$u")"
  rm -f "$tmp"
done
sudo systemctl daemon-reload
sudo systemctl enable --now mealboard-api mealboard-mock mealboard-neis.timer mealboard-news.timer
echo ">> 카메라 있는 Pi 에서만:  sudo systemctl disable --now mealboard-mock && sudo systemctl enable --now mealboard-vision"

echo "== 완료. 확인:  curl -s localhost:\${API_PORT:-8100}/api/status"
