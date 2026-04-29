import secrets
from datetime import datetime
import click
from flask import Flask, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from sqlalchemy import MetaData

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Tenes que iniciar sesion."
login_manager.login_message_category = "error"


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

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

    from app import routes, auth, reports
    app.register_blueprint(routes.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(reports.bp)

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
