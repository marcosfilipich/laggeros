# Laggeros

Ranking de cuanto laggean los integrantes del grupo "capos" en sus partidas. Aplica para todos los juegos.

## Stack
- Python 3.10+ / Flask 3
- SQLAlchemy
- SQLite (dev) / MySQL (prod)
- Gunicorn + Nginx en produccion

## Setup local (Windows)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
flask --app wsgi:app init-db
flask --app wsgi:app seed
python wsgi.py
```

Abrir http://localhost:5000

## Setup en produccion

Ver instrucciones de deploy en el server (nginx + gunicorn + systemd + MySQL).

Variables de entorno en prod:
- `SECRET_KEY` (random)
- `DATABASE_URL` (`mysql+pymysql://user:pass@host/db`)

## Estructura

```
app/
  __init__.py    # factory + CLI commands
  models.py      # Player, Game, LagReport
  routes.py      # views
  templates/     # Jinja2
  static/        # CSS
config.py
wsgi.py          # entry point
```

## Comandos utiles

```bash
flask --app wsgi:app init-db    # crear tablas
flask --app wsgi:app seed       # cargar players y juegos por defecto
```
