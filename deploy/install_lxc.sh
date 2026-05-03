#!/usr/bin/env bash
#
# BotPanel — installation dans un conteneur LXC (Debian/Ubuntu).
#
# A executer dans le conteneur :
#   curl -fsSL https://.../install_lxc.sh | bash -s -- https://github.com/user/botpanel.git
# Ou localement apres avoir copie le repo dans /opt/botpanel :
#   sudo bash deploy/install_lxc.sh
#
set -euo pipefail

INSTALL_DIR="/opt/botpanel"
SERVICE_USER="botpanel"
REPO_URL="${1:-}"

echo ">>> [1/6] Dependances systeme"
apt-get update -y
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip git ca-certificates

echo ">>> [2/6] Utilisateur systeme"
if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    useradd --system --shell /usr/sbin/nologin --home "${INSTALL_DIR}" "${SERVICE_USER}"
fi

echo ">>> [3/6] Code source"
if [ -n "${REPO_URL}" ]; then
    if [ -d "${INSTALL_DIR}/.git" ]; then
        git -C "${INSTALL_DIR}" pull
    else
        git clone "${REPO_URL}" "${INSTALL_DIR}"
    fi
fi
mkdir -p "${INSTALL_DIR}/data"

echo ">>> [4/6] Venv Python + dependances"
python3 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

echo ">>> [5/6] .env"
if [ ! -f "${INSTALL_DIR}/.env" ]; then
    cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
    echo "!! Editer ${INSTALL_DIR}/.env avec tes tokens/IP avant de demarrer."
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
chmod 640 "${INSTALL_DIR}/.env"

echo ">>> [6/6] systemd"
cp "${INSTALL_DIR}/deploy/botpanel.service" /etc/systemd/system/botpanel.service
systemctl daemon-reload
systemctl enable botpanel.service

echo ">>> [extra] sudoers (restart auto depuis l'UI)"
SUDOERS_FILE="/etc/sudoers.d/botpanel-restart"
echo "${SERVICE_USER} ALL=NOPASSWD: /bin/systemctl restart botpanel" > "${SUDOERS_FILE}"
chmod 440 "${SUDOERS_FILE}"
visudo -c -f "${SUDOERS_FILE}" >/dev/null
echo "OK : ${SERVICE_USER} peut faire 'sudo systemctl restart botpanel' sans mot de passe."

echo ""
echo "Installation terminee."
echo "  1. Editer /opt/botpanel/.env"
echo "  2. systemctl start botpanel"
echo "  3. journalctl -u botpanel -f   (pour suivre les logs)"
