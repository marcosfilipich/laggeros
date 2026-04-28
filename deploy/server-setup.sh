#!/bin/bash
# Laggeros - Server setup script para Ubuntu 24.04
# Uso:
#   sudo DUCKDNS_TOKEN=tu-token DUCKDNS_DOMAIN=laggeros bash deploy/server-setup.sh
#
# Idempotente: podes correrlo multiples veces sin romper nada.

set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "Correr con sudo: sudo bash deploy/server-setup.sh"
    exit 1
fi

DUCKDNS_TOKEN="${DUCKDNS_TOKEN:-}"
DUCKDNS_DOMAIN="${DUCKDNS_DOMAIN:-laggeros}"
APP_USER="${APP_USER:-marcos}"
APP_DIR="${APP_DIR:-/home/${APP_USER}/laggeros}"
APP_NAME="laggeros"
SERVER_NAME="${DUCKDNS_DOMAIN}.duckdns.org"

if [ -z "$DUCKDNS_TOKEN" ]; then
    echo "ERROR: setea DUCKDNS_TOKEN. Ejemplo:"
    echo "  sudo DUCKDNS_TOKEN=xxx DUCKDNS_DOMAIN=laggeros bash deploy/server-setup.sh"
    exit 1
fi

if [ ! -d "$APP_DIR" ]; then
    echo "ERROR: $APP_DIR no existe. Cloná el repo primero como user $APP_USER:"
    echo "  git clone https://github.com/marcosfilipich/laggeros.git $APP_DIR"
    exit 1
fi

echo ">>> 1/8 Instalando paquetes del sistema..."
export DEBIAN_FRONTEND=noninteractive
apt update -qq
apt install -y -qq \
    python3-venv python3-pip python3-dev build-essential \
    mysql-server default-libmysqlclient-dev pkg-config \
    nginx \
    ufw \
    curl

echo ">>> 2/8 Configurando MySQL..."
systemctl enable --now mysql
DB_NAME="laggeros"
DB_USER="laggeros"
DB_PASS_FILE="/etc/laggeros/db_password"
mkdir -p /etc/laggeros
chmod 750 /etc/laggeros

if [ ! -f "$DB_PASS_FILE" ]; then
    DB_PASS=$(openssl rand -hex 24)
    echo "$DB_PASS" > "$DB_PASS_FILE"
    chmod 600 "$DB_PASS_FILE"
    echo "    Password de DB generado y guardado en $DB_PASS_FILE"
else
    DB_PASS=$(cat "$DB_PASS_FILE")
    echo "    Reusando password de DB en $DB_PASS_FILE"
fi

mysql --protocol=socket -uroot <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL

echo ">>> 3/8 Configurando DuckDNS..."
DUCK_DIR="/home/${APP_USER}/duckdns"
sudo -u "$APP_USER" mkdir -p "$DUCK_DIR"
cat > "$DUCK_DIR/duck.sh" <<EOF
#!/bin/bash
echo url="https://www.duckdns.org/update?domains=${DUCKDNS_DOMAIN}&token=${DUCKDNS_TOKEN}&ip=" | curl -k -o ${DUCK_DIR}/duck.log -K -
EOF
chown "$APP_USER:$APP_USER" "$DUCK_DIR/duck.sh"
chmod 700 "$DUCK_DIR/duck.sh"
sudo -u "$APP_USER" "$DUCK_DIR/duck.sh"
echo "    DuckDNS update result: $(cat $DUCK_DIR/duck.log)"

CRON_LINE="*/5 * * * * $DUCK_DIR/duck.sh >/dev/null 2>&1"
sudo -u "$APP_USER" bash -c "(crontab -l 2>/dev/null | grep -v duckdns; echo \"$CRON_LINE\") | crontab -"

echo ">>> 4/8 Setup del Python venv y dependencias..."
sudo -u "$APP_USER" bash <<EOF
cd "$APP_DIR"
git pull --rebase || true
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
EOF

echo ">>> 5/8 Generando .env de produccion..."
ENV_FILE="$APP_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    SECRET_KEY=$(openssl rand -hex 32)
    cat > "$ENV_FILE" <<EOF
FLASK_APP=wsgi:app
SECRET_KEY=${SECRET_KEY}
DATABASE_URL=mysql+pymysql://${DB_USER}:${DB_PASS}@localhost/${DB_NAME}
EOF
    chown "$APP_USER:$APP_USER" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "    .env creado con SECRET_KEY y DATABASE_URL"
else
    echo "    .env ya existe, no lo toco"
fi

echo ">>> 6/8 Inicializando base de datos..."
sudo -u "$APP_USER" bash <<EOF
cd "$APP_DIR"
set -a; . .env; set +a
.venv/bin/flask --app wsgi:app init-db
.venv/bin/flask --app wsgi:app seed
EOF

echo ">>> 7/8 Configurando systemd service para gunicorn..."
cat > /etc/systemd/system/${APP_NAME}.service <<EOF
[Unit]
Description=Laggeros Flask app (gunicorn)
After=network.target mysql.service

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/gunicorn -w 3 -b 127.0.0.1:8000 wsgi:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${APP_NAME}
systemctl restart ${APP_NAME}
sleep 2
systemctl is-active ${APP_NAME} >/dev/null && echo "    gunicorn corriendo OK" || (journalctl -u ${APP_NAME} -n 30 --no-pager; exit 1)

echo ">>> 8/8 Configurando nginx..."
cat > /etc/nginx/sites-available/${APP_NAME} <<EOF
server {
    listen 80;
    server_name ${SERVER_NAME};

    client_max_body_size 4M;

    location /static/ {
        alias ${APP_DIR}/app/static/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/${APP_NAME} /etc/nginx/sites-enabled/${APP_NAME}
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo ">>> Configurando UFW..."
ufw --force allow OpenSSH
ufw --force allow 'Nginx HTTP'
ufw --force enable

echo ""
echo "============================================"
echo " DEPLOY OK"
echo "============================================"
echo " URL:        http://${SERVER_NAME}"
echo " App:        ${APP_DIR}"
echo " Service:    systemctl status ${APP_NAME}"
echo " Logs:       journalctl -u ${APP_NAME} -f"
echo " DB:         mysql -u${DB_USER} -p (pass en ${DB_PASS_FILE})"
echo "============================================"
