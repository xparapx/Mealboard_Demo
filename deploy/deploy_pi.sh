#!/usr/bin/env bash
# deploy_pi.sh — Pi 배포 한 방(09-12 운영 구조: 로컬 커밋 → push → Pi 는 이 스크립트만)
# 사용: /opt/mealboard 에서  bash deploy/deploy_pi.sh [--with-vision]
#   --with-vision : mealboard-vision 도 재시작(급식 시간에는 카운팅 공백 — 시간 확인 후에만)
set -euo pipefail
cd "$(dirname "$0")/.."

WITH_VISION=0
[ "${1:-}" = "--with-vision" ] && WITH_VISION=1

# 작업트리는 항상 clean 이어야 한다 — 오염돼 있으면 배포 거부(Pi 직접 편집 금지 규칙)
if [ -n "$(git status --porcelain)" ]; then
  echo "[중단] 작업트리가 clean 이 아니다 — Pi 에서 직접 편집하지 않는 규칙 위반 여부부터 확인:" >&2
  git status --short >&2
  exit 1
fi

BEFORE=$(git rev-parse HEAD)
git pull --ff-only
AFTER=$(git rev-parse HEAD)

if [ "$BEFORE" = "$AFTER" ]; then
  echo "[정보] 새 커밋 없음($(git log --oneline -1))."
fi
CHANGED=$(git diff --name-only "$BEFORE" "$AFTER")

# 의존성 변경 → uv sync (vision extra 필수: 맨 sync 가 ultralytics 등을 지운다)
if echo "$CHANGED" | grep -qE '^(pyproject\.toml|uv\.lock)$'; then
  echo "[단계] 의존성 변경 → uv sync --extra vision"
  uv sync --extra vision
fi

# 유닛·설치 절차 변경 → setup_pi.sh (멱등)
if echo "$CHANGED" | grep -qE '^(deploy/.*\.(service|timer)|setup_pi\.sh)$'; then
  echo "[단계] 유닛 변경 → setup_pi.sh"
  bash setup_pi.sh
fi

echo "[단계] 서비스 재시작: api, admin"
sudo systemctl restart mealboard-api mealboard-admin

if [ "$WITH_VISION" = 1 ]; then
  echo "[단계] 서비스 재시작: vision (--with-vision)"
  sudo systemctl restart mealboard-vision
else
  echo "[정보] vision 은 재시작하지 않음(필요 시 --with-vision, 급식 시간 주의)."
fi

echo "[검증] /api/status"
sleep 2
CODE=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8100/api/status)
if [ "$CODE" = "200" ]; then
  echo "[완료] $(git log --oneline -1) · /api/status 200"
else
  echo "[경고] /api/status HTTP $CODE — journalctl -u mealboard-api -n 50 확인" >&2
  exit 1
fi
