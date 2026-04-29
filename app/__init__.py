import secrets
from datetime import datetime
import click
from flask import Flask, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from sqlalchemy import MetaData
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Tenes que iniciar sesion."
login_manager.login_message_category = "error"


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    # Confiamos en los headers X-Forwarded-* de nginx (1 hop). Sin esto Flask
    # cree que el request es HTTP y SESSION_COOKIE_SECURE no manda la cookie.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_for=1, x_host=1)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import Usuario
        return Usuario.query.get(int(user_id))

    @app.before_request
    def force_password_change():
        if not current_user.is_authenticated:
            return
        if not current_user.must_change_password:
            return
        allowed = {"auth.change_password", "auth.logout", "static"}
        if request.endpoint in allowed:
            return
        return redirect(url_for("auth.change_password"))

    @app.before_request
    def force_onboarding():
        if not current_user.is_authenticated:
            return
        if current_user.must_change_password:
            return  # otro before_request ya redirige a cambiar password
        if current_user.has_seen_about:
            return
        ep = request.endpoint or ""
        if ep == "main.about" or ep.startswith("main.about_"):
            return
        if ep == "auth.logout" or ep == "static":
            return
        return redirect(url_for("main.about_ranking"))

    from app import routes, auth, reports, appeals
    app.register_blueprint(routes.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(appeals.bp)

    @app.template_filter("relative_days")
    def relative_days(dt):
        if dt is None:
            return "-"
        days = (datetime.utcnow() - dt).days
        if days <= 0:
            return "hace menos de 1 dia"
        if days == 1:
            return "hace 1 dia"
        return f"hace {days} dias"

    @app.context_processor
    def inject_pending_review_count():
        if not current_user.is_authenticated:
            return {"pending_review_count": 0}
        from sqlalchemy import func, and_
        from app.models import Report, ReportReviewer, Vote
        count = (
            db.session.query(func.count(Report.id.distinct()))
            .join(ReportReviewer, ReportReviewer.report_id == Report.id)
            .outerjoin(Vote, and_(Vote.report_id == Report.id,
                                  Vote.usuario_id == current_user.id))
            .filter(Report.status == "pending")
            .filter(ReportReviewer.usuario_id == current_user.id)
            .filter(Vote.id.is_(None))
            .scalar()
        ) or 0
        return {"pending_review_count": count}

    @app.context_processor
    def inject_pending_appeal_count():
        if not current_user.is_authenticated:
            return {"pending_appeal_count": 0}
        from app.models import Appeal, AppealVote, Report, Vote
        # Subquery: report_ids donde current_user voto SI en el original
        yes_on_orig = (
            db.session.query(Vote.report_id)
            .filter(Vote.usuario_id == current_user.id, Vote.vote == "yes")
        )
        # Subquery: appeal_ids donde current_user ya voto
        already_voted = (
            db.session.query(AppealVote.appeal_id)
            .filter(AppealVote.usuario_id == current_user.id)
        )
        count = (
            Appeal.query
            .join(Report, Report.id == Appeal.report_id)
            .filter(Appeal.status == "pending")
            .filter(Appeal.appealer_id != current_user.id)
            .filter(Report.reporter_id != current_user.id)
            .filter(~Appeal.report_id.in_(yes_on_orig))
            .filter(~Appeal.id.in_(already_voted))
            .count()
        )
        return {"pending_appeal_count": count}

    @app.cli.command("init-db")
    def init_db():
        from app import models  # noqa: F401
        db.create_all()
        print("Database initialized.")

    @app.cli.command("seed")
    def seed():
        from app.models import Usuario
        # nickname, nombre_real, rol
        defaults = [
            ("Queso", "Marcos", "player"),
            ("Ghiro", "Ghiro", "player"),
            ("Ando", "Ando", "player"),
            ("Pyrook", "Nacho", "player"),
            ("Tompson", "Tompson", "player"),
            ("Lommi", "Lommi", "player"),
            ("Feri", "Federico", "player"),
            ("Pancho", "Pancho", "player"),
            ("Marqui", "Marcos", "player"),
            ("Juani", "Juani", "player"),
            ("Lucho", "Lucho", "player"),
            ("Opro", "Lucas", "player"),
        ]
        added = 0
        for nickname, nombre_real, rol in defaults:
            if not Usuario.query.filter_by(nickname=nickname).first():
                db.session.add(Usuario(nickname=nickname, nombre_real=nombre_real, rol=rol))
                added += 1

        # Admin user con password "admin" (no fuerza cambio para usar admin/admin directo)
        admin = Usuario.query.filter_by(nickname="admin").first()
        if admin is None:
            admin = Usuario(nickname="admin", nombre_real=None, rol="admin", must_change_password=False)
            admin.set_password("admin")
            db.session.add(admin)
            added += 1

        db.session.commit()
        print(f"Seeded {added} new usuario(s) (skipped existing).")

    @app.cli.command("reset-db")
    @click.confirmation_option(prompt="Esto borra TODAS las tablas y datos. Seguro?")
    def reset_db():
        from app import models  # noqa: F401
        meta = MetaData()
        meta.reflect(bind=db.engine)
        meta.drop_all(bind=db.engine)
        db.create_all()
        print(f"Database reset: dropped {len(meta.tables)} table(s), recreated current schema.")

    @app.cli.command("set-password")
    @click.argument("nickname")
    @click.argument("password")
    def set_password_cmd(nickname, password):
        from app.models import Usuario
        u = Usuario.query.filter_by(nickname=nickname).first()
        if not u:
            print(f"Usuario '{nickname}' no encontrado.")
            return
        u.set_password(password)
        u.must_change_password = True
        db.session.commit()
        print(f"Password seteada para '{nickname}' (debe cambiarla en el primer login).")

    @app.cli.command("reset-onboarding")
    @click.option("--only-players/--all", default=True, help="Solo players (default) o tambien admin")
    def reset_onboarding(only_players):
        """Marca a todos los usuarios con has_seen_about=False para que vuelvan a ver el onboarding."""
        from app.models import Usuario
        q = Usuario.query
        if only_players:
            q = q.filter(Usuario.rol == "player")
        rows = q.all()
        for u in rows:
            u.has_seen_about = False
        db.session.commit()
        print(f"Reset onboarding para {len(rows)} usuario(s).")

    @app.cli.command("init-passwords")
    def init_passwords():
        """Genera passwords random para todos los usuarios sin password seteada."""
        from app.models import Usuario
        rows = Usuario.query.order_by(Usuario.id).all()
        print()
        print(f"{'Nickname':<12} {'Nombre':<18} {'Rol':<8} Password inicial")
        print("-" * 70)
        for u in rows:
            if u.password_hash:
                print(f"{u.nickname:<12} {u.nombre_real or '-':<18} {u.rol:<8} (ya tiene password)")
                continue
            pw = secrets.token_urlsafe(6)
            u.set_password(pw)
            u.must_change_password = True
            print(f"{u.nickname:<12} {u.nombre_real or '-':<18} {u.rol:<8} {pw}")
        db.session.commit()
        print()
        print("Compartir estas passwords con cada usuario. Las van a tener que cambiar al primer login.")

    return app
