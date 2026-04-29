# Laggeros — context file

Sistema de "ranking de lag" peer-reviewed para un grupo de 11 amigos
("capos") más una cuenta admin. Cualquier player puede acusar a otro
de laggear, los demás votan, y si se aprueba se le suman puntos al
acusado en el ranking.

URL prod: https://laggeros.duckdns.org  (HTTP redirige automaticamente a HTTPS)
Repo: https://github.com/marcosfilipich/laggeros (público)

---

## Stack

- Python 3.13 + Flask 3
- SQLAlchemy + Flask-SQLAlchemy + Flask-Login
- MySQL 8 (corre en un container Docker compartido `kintrack-mysql` en
  el server, no instalado por apt)
- PyMySQL como driver (puro Python, no requiere libs C)
- Gunicorn detrás de nginx
- Werkzeug para hash de passwords
- Sin ORM migrations (no Alembic) — los cambios de schema se hacen con
  `ALTER TABLE` manual (ver "Migraciones")

## Infra (server)

- Linode `prod` (id 82242788), Ubuntu 24.04, IP `172.237.63.56`
- SSH user app: `marcos` (con sudo); también hay deploy key
  `~/.ssh/laggeros_deploy` localmente para auto-deploy / SSH desde scripts
- App vive en `/home/marcos/laggeros`
- Entorno via `.env` en ese directorio (`DATABASE_URL`, `SECRET_KEY`,
  `UPLOAD_FOLDER`, `SESSION_COOKIE_SECURE=true`,
  `REMEMBER_COOKIE_SECURE=true`); password de DB también en
  `/etc/laggeros/db_password`
- Servicio systemd: `laggeros` (gunicorn `wsgi:app` en `127.0.0.1:8000`,
  3 workers)
- nginx en `/etc/nginx/sites-available/laggeros`: proxy a gunicorn,
  sirve `/static/` directo; uploads van por Flask (login_required).
  `client_max_body_size 25M`. Listen 443 con cert de Let's Encrypt y
  redirect 80 -> 443.
- HTTPS via Let's Encrypt + certbot (paquete `python3-certbot-nginx`):
  cert en `/etc/letsencrypt/live/laggeros.duckdns.org/`. Auto-renovacion
  via systemd timer `certbot.timer` (revisa diario, renueva ~30 dias antes
  de expirar; reload nginx via deploy hook). Para forzar renovacion ad-hoc:
  `sudo certbot renew` o `sudo certbot renew --dry-run`.
- ProxyFix middleware en `app/__init__.py` lee `X-Forwarded-Proto` que
  manda nginx asi Flask sabe que el request es HTTPS (sin esto las
  cookies con `SECURE=True` no se mandan).
- DuckDNS: cron cada 5 min en `~/duckdns/duck.sh` actualiza la IP
- Firewall UFW: SSH y "Nginx Full" abiertos (Nginx Full = 80 + 443);
  resto cerrado
- Sudoers `marcos`: NOPASSWD para `systemctl restart laggeros`,
  `systemctl is-active laggeros`, `journalctl -u laggeros`, `nginx -t`,
  `systemctl reload nginx`

## Auto-deploy

- GitHub Actions workflow `.github/workflows/deploy.yml`
- Dispara en cada push a `main`
- Hace SSH al server con la deploy key (secret `SSH_PRIVATE_KEY` en
  GitHub) y corre `bash deploy/deploy-update.sh`
- Para saltarlo (e.g. cuando hay que migrar antes), incluir `[skip ci]`
  en el commit message
- `deploy/server-setup.sh` es el setup inicial (idempotente). Solo se
  corre una vez al provisionar.

---

## DB schema

```
usuarios
  id              INT pk
  nickname        VARCHAR(80) unique
  nombre_real     VARCHAR(120) nullable
  password_hash   VARCHAR(255) nullable
  must_change_password BOOL  -- forced password change on first login
  rol             VARCHAR(20) 'player' | 'admin'  (admin no aparece en ranking)
  reportes_falsos_count INT default 0  -- cuenta de reports rechazados;
                                       -- al llegar a 3, reset + 3 pts al user
  has_seen_about  BOOL  -- false bloquea al user en /about/* hasta que confirme

puntos
  id              INT pk
  player_id       INT fk -> usuarios.id  (nombre legacy de cuando se llamaba 'players')
  points          INT
  date_inserted   DATETIME

reports
  id              INT pk
  reporter_id     INT fk -> usuarios.id  (creador)
  target_id       INT fk -> usuarios.id  (acusado)
  points          INT 1..10              (severidad propuesta)
  description     TEXT
  evidence_text   TEXT nullable          (legacy, ya no se llena via form;
                                          mostrado en detail si existe)
  status          VARCHAR(20) 'pending' | 'approved' | 'rejected' | 'cancelled'
  created_at      DATETIME

report_reviewers           (m2m)
  id              INT pk
  report_id       INT fk -> reports.id
  usuario_id      INT fk -> usuarios.id
  UNIQUE(report_id, usuario_id)

report_attachments
  id              INT pk
  report_id       INT fk -> reports.id
  filename        VARCHAR(255)   -- nombre uuid en disco (bajo UPLOAD_FOLDER)
  original_name   VARCHAR(255)
  mime_type       VARCHAR(80)
  size_bytes      INT
  uploaded_at     DATETIME

votes
  id              INT pk
  report_id       INT fk -> reports.id
  usuario_id      INT fk -> usuarios.id
  vote            VARCHAR(10) 'yes' | 'no'
  comment         TEXT nullable
  voted_at        DATETIME
  UNIQUE(report_id, usuario_id)         -- 1 voto por user por reporte;
                                        -- el voto es FINAL, no se puede cambiar

comments
  id              INT pk
  report_id       INT fk -> reports.id
  usuario_id      INT fk -> usuarios.id
  parent_id       INT fk -> comments.id nullable   -- self-referential para threading
  body            TEXT
  created_at      DATETIME
```

Cascades: `Report.reviewers/attachments/votes/comments` y `Usuario.puntos`
usan `cascade="all, delete-orphan"` a nivel ORM. Cuando borrás un Report
via SQLAlchemy se eliminan sus hijos. Para SQL crudo conviene
`SET FOREIGN_KEY_CHECKS=0` antes de truncate.

---

## Código

```
app/
  __init__.py     factory, LoginManager, 2 before_request hooks
                  (force_password_change, force_onboarding), CLI commands,
                  template filters (relative_days), context_processor
                  (pending_review_count para badges)
  models.py       Usuario, Punto, Report, ReportReviewer, ReportAttachment,
                  Vote, Comment
  auth.py         /auth blueprint: login, logout, change-password
                  (cambia password una vez bajo template auth/login.html
                  y uno de change_password_forced.html / change_password.html
                  segun must_change_password)
  routes.py       'main' blueprint: index (ranking + streaks), history,
                  about/* (5 sub-tabs), about_done (POST marca has_seen_about)
  reports.py      'reports' blueprint: list_reports redirect, active/pending/
                  closed/new/<id>/<id>/vote/<id>/comment/uploads;
                  helpers _comment_counts, _attachment_counts,
                  _check_and_apply_decision, _apply_approval, _apply_rejection
  static/
    style.css     todo el estilo (dark theme, accent rojo #e63946)
  templates/
    base.html             layout autenticado: header sticky, sidebar
                          (con badge de pending review counts) +
                          About pinned-bottom, main + footer
    base_auth.html        layout standalone para login y forced-change-password
    index.html            ranking con columna 'Racha' (streaks)
    history.html          ultimos 100 puntos aplicados
    auth/
      login.html
      change_password_forced.html       primer login (sin sidebar)
      change_password.html              voluntario (con sidebar, vive
                                        bajo "Configuracion" tab)
    reports/
      _subnav.html        active / pending / closed / + Generar reporte
                          (este ultimo flotando a la derecha como CTA roja)
      list.html
      new.html            form: target select, points (1-10), description,
                          adjuntos (multiple, max 3 x 5MB), reviewers
                          (toggle pills, min 2, target auto-disabled)
      detail.html         meta + description + evidence + attachments +
                          reviewers chips (con marca yes/no si votaron) +
                          progress block (X/Y reviewers SI, X/6 total SI) +
                          tu voto (form, una vez, con confirm()) +
                          votes list +
                          comments thread con macro recursivo render_comment;
                          replies > 3 muestran 3 + boton "Mostrar N mas"
    about/
      _subnav.html        Ranking | Reportes | Reviewer | Votaciones | Rachas
                          (incluye _onboarding_banner.html arriba si
                          has_seen_about=False)
      _onboarding_banner.html       banner rojo de bienvenida
      _onboarding_action.html       boton 'Listo, llevame al ranking'
                                    (incluido al pie de cada about page)
      ranking.html / reportes.html / reviewer.html /
      votaciones.html / rachas.html
config.py         BASE_DIR, DATABASE_URL, SECRET_KEY, UPLOAD_FOLDER,
                  MAX_CONTENT_LENGTH (20MB)
wsgi.py           entry point (load_dotenv + create_app + run dev server)
deploy/
  server-setup.sh        provisioning (apt, mysql en docker, env, systemd, nginx, ufw)
  deploy-update.sh       git pull + pip install + systemctl restart laggeros
  README.md              one-page con instrucciones de setup/update
.github/workflows/deploy.yml       auto-deploy via appleboy/ssh-action
```

## Mechanics

- **Crear reporte**: cualquier player crea, no se puede a si mismo.
  Reviewers minimo 2, no incluyen reporter ni target. Adjuntos max 3,
  hasta 5MB c/u, jpg/png/gif/webp/pdf.
- **Voto**: cualquier player MENOS reporter y target. Una sola vez,
  yes o no, comentario opcional. Confirm modal pre-submit.
- **Aprobacion** (status -> approved, +N puntos al target):
  todos los reviewers asignados votaron SI **o** ≥ 6 votos SI totales
  (de cualquier player).
- **Rechazo** (status -> rejected): ≥ 5 votos NO. Incrementa
  `reporter.reportes_falsos_count`; al llegar a 3, reset a 0 + 3 puntos
  al reporter como castigo (también aparece como Punto en el historial).
- **Constantes** en `app/reports.py`: `TOTAL_YES_THRESHOLD = 6`,
  `NO_REJECTION_THRESHOLD = 5`, `FALSE_REPORTS_THRESHOLD = 3`,
  `FALSE_REPORTS_PENALTY_POINTS = 3`.
- **Streaks** (en columna "Racha" del ranking, calculadas en
  `app.routes._compute_streak`):
  - 🔥 azul: `(now - last_punto).days >= 10` -> "X dias sin laggearla"
  - 🔥 rojo: chain de >= 2 puntos consecutivos con gap <= 48h y el
    ultimo a <= 48h de ahora -> "Lleva X dias laggeandola"
  - El emoji 🔥 azul se logra con CSS `filter: hue-rotate(180deg) saturate(2)`
- **Onboarding**: `force_onboarding` redirige cualquier endpoint que no
  sea `main.about*` o `auth.logout` a `/about/ranking` mientras
  `has_seen_about=False`. Confirma con POST a `/about/done`.
- **Comments threading**: macro recursiva en `detail.html`. Para cada
  comentario: muestra hasta 3 hijos directos, si hay mas, boton
  "Mostrar N respuestas mas" expande el resto via JS toggleMore.
- **Notification badges**: context_processor calcula
  `pending_review_count` (reportes pending donde el user es reviewer y
  no votó). El sidebar item "Reportes" y el sub-tab "Reportes
  pendientes" muestran un badge rojo pulsante con el numero.

## CLI commands (bajo `flask --app wsgi:app ...`)

```
init-db                 db.create_all() — solo crea tablas que no existan
seed                    inserta los 11 players + admin si faltan
                        (idempotente, skip-existing)
reset-db                drop_all + create_all  (destructivo, requiere --yes)
set-password NICK PASS  setea password manual; marca must_change_password=True
init-passwords          genera passwords random para users sin password,
                        las imprime en pantalla, marca must_change_password=True
reset-onboarding        marca has_seen_about=False
                        (--only-players default, --all incluye admin)
```

## Tareas comunes

### Cambiar el código
1. Edit local
2. `git push` -> auto-deploy corre solo
3. Verificar:
   `gh run list --repo marcosfilipich/laggeros --limit 1 --json conclusion`

### Migrar schema (sin reset)
1. Editar el modelo
2. Commit con `[skip ci]` (para que NO dispare auto-deploy todavia)
3. SSH al server y correr en una sola pasada:
   - migration SQL via Python (`db.session.execute(text("ALTER TABLE..."))`)
   - `bash deploy/deploy-update.sh` (pull + restart)
   - cualquier post-migration data fix
   Patron usado varias veces ya (ver historial de commits con `[skip ci]`).

### Resetear datos sin perder usuarios
```
SET FOREIGN_KEY_CHECKS=0;
TRUNCATE votes; TRUNCATE comments; TRUNCATE report_attachments;
TRUNCATE report_reviewers; TRUNCATE reports; TRUNCATE puntos;
SET FOREIGN_KEY_CHECKS=1;
UPDATE usuarios SET reportes_falsos_count=0, has_seen_about=0 WHERE rol='player';
rm -f ~/laggeros/uploads/*
```

### Lanzar para players (post-reset de datos)
1. Verificar reset completo (todas las tablas excepto usuarios = 0,
   uploads vacio, todos los players con `has_seen_about=False`)
2. Avisar a los players por whatsapp con su password ya conocida
3. Cada uno entra, ve el banner de bienvenida en `/about/ranking`,
   navega las 5 secciones, toca "Listo", queda habilitado para usar la app

## Diseño visual

- **Inspiración**: promiedos.com.ar — dark theme, tablas densas, sin
  esquinas redondeadas (border-radius: 2-3px máximo), tipografía pequeña
  (font-size base 13px)
- **Variables CSS** (en `app/static/style.css`):
  - `--bg-primary #0f1216`, `--bg-secondary #1a1d24`, `--bg-tertiary #232730`
  - `--accent #e63946` (rojo), `--accent-hover #ff4d5c`
  - `--text-primary #ffffff`, `--text-secondary #9ba0a8`,
    `--text-muted #6b7080`
  - `--border #2a2f3a`
- **Layout**: header sticky en top + sidebar 220px (sticky bajo el header,
  con About pinned al fondo) + main flex 1
- **Mobile** (<768px): sidebar pasa arriba del contenido (no sticky)

## Cosas a tener en cuenta

- Las contraseñas iniciales que generó `init-passwords` ya fueron
  distribuidas y los users las cambiaron. NO volver a correr ese comando
  (sobreescribiría passwords).
- El usuario `admin` tiene password literal `admin` (V0). Cambiar cuando
  el user lo decida; está en backlog.
- DuckDNS token: el original (`6f7f8317-...`) fue posteado en chat. El
  user iba a regenerarlo. Si hay que actualizar el cron en el server,
  editar `~/duckdns/duck.sh` con el token nuevo.
- `linode.txt` en el repo local del user contiene el password de root
  del Linode (`HelicopteroAlienigena14-`). Está en `.gitignore` para que
  no llegue al repo.
- `evidence_text` en `Report` es legacy (campo deprecado del form pero
  la columna sigue por si hay datos viejos).
- `Punto.player_id` también es legacy del rename de `players` a
  `usuarios`. La columna apunta a `usuarios.id` pero conserva el nombre
  viejo.
