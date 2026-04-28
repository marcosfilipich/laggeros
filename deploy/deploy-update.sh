#!/bin/bash
# Laggeros - Update script (correr como user marcos, NO sudo)
# Hace git pull, instala deps si cambiaron, y reinicia gunicorn.

set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/laggeros}"
APP_NAME="laggeros"

cd "$APP_DIR"
echo ">>> git pull..."
git pull --rebase

echo ">>> Actualizando dependencias..."
.venv/bin/pip install --quiet -r requirements.txt

echo ">>> Reiniciando ${APP_NAME}..."
sudo systemctl restart ${APP_NAME}
sleep 2
sudo systemctl is-active ${APP_NAME} >/dev/null && echo "OK, gunicorn corriendo" || (sudo journalctl -u ${APP_NAME} -n 30 --no-pager; exit 1)
