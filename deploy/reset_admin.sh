#!/usr/bin/env bash
# Reinitialise le mot de passe admin de BotPanel (secours en cas d'oubli).
#
#   ./reset_admin.sh              -> supprime le mot de passe (panel de nouveau ouvert)
#   ./reset_admin.sh "nouveau"    -> definit un nouveau mot de passe
#
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

PY="$DIR/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

"$PY" -m app.reset_admin "$@"

echo ""
echo "-> Redemarre le service : sudo systemctl restart botpanel"
