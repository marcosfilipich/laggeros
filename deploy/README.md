# Deploy

## Setup inicial del servidor (una sola vez)

En tu PC, asegurate de haber pusheado los cambios al repo. Despues, en el server:

```bash
ssh marcos@172.237.63.56
git clone https://github.com/marcosfilipich/laggeros.git
cd laggeros
sudo DUCKDNS_TOKEN=tu-token DUCKDNS_DOMAIN=laggeros bash deploy/server-setup.sh
```

El script:
- Instala Python, MySQL, nginx, ufw
- Crea la base `laggeros` y un user con password random
- Configura DuckDNS + cron (actualiza la IP cada 5 min)
- Crea venv, instala deps, genera `.env` con `SECRET_KEY` y `DATABASE_URL`
- Inicializa la DB y carga seed (Marcos, Capo1, Capo2 + CS2/Valorant/LoL/Fortnite)
- Levanta gunicorn como systemd service (`laggeros`)
- Configura nginx para `laggeros.duckdns.org` -> gunicorn
- Abre firewall (SSH + HTTP)

## Updates futuros (cada vez que cambia el codigo)

En tu PC: `git push` los cambios. En el server:

```bash
ssh marcos@172.237.63.56
cd laggeros
bash deploy/deploy-update.sh
```

## Comandos utiles en el server

```bash
sudo systemctl status laggeros        # estado del service
sudo systemctl restart laggeros       # reiniciar
sudo journalctl -u laggeros -f        # ver logs en tiempo real
sudo nginx -t && sudo systemctl reload nginx   # recargar nginx tras editar config
mysql -ulaggeros -p                   # conectar a la DB (pass en /etc/laggeros/db_password)
```

## Troubleshooting

- **502 Bad Gateway en nginx**: gunicorn no esta corriendo. `sudo systemctl status laggeros` y ver logs.
- **Pagina no carga (timeout)**: revisar UFW (`sudo ufw status`) y que el dominio apunte al server (`dig +short laggeros.duckdns.org`).
- **DB connection error**: revisar `.env` y que MySQL este corriendo (`sudo systemctl status mysql`).
