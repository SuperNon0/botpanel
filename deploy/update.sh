#!/usr/bin/env bash
# BotPanel — mise à jour
# Usage manuel : sudo bash /opt/botpanel/deploy/update.sh
# Usage web UI : sudo bash /opt/botpanel/deploy/update.sh --no-restart
set -euo pipefail

APP_DIR="/opt/botpanel"
APP_USER="botpanel"
RESTART=true

for arg in "$@"; do
  [ "$arg" = "--no-restart" ] && RESTART=false
done

echo "==> [$(date '+%H:%M:%S')] Démarrage de la mise à jour..."

echo "==> Correction des permissions..."
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo "==> Git fetch..."
sudo -u "${APP_USER}" git -C "${APP_DIR}" fetch origin main

echo "==> Git reset vers origin/main..."
sudo -u "${APP_USER}" git -C "${APP_DIR}" checkout main
sudo -u "${APP_USER}" git -C "${APP_DIR}" reset --hard origin/main

echo "==> Mise à jour des dépendances Python..."
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -q -r "${APP_DIR}/requirements.txt"

if [ "$RESTART" = "true" ]; then
  echo "==> Redémarrage du service..."
  systemctl restart botpanel
  sleep 2
  systemctl is-active botpanel && echo "==> Service actif ✓" || echo "==> ERREUR : service inactif"
fi

echo "==> [$(date '+%H:%M:%S')] Mise à jour terminée."
