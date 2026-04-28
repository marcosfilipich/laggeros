import secrets
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
        from app.models import Player
        return Player.query.get(int(user_id))

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

    from app import routes, auth
    app.register_blueprint(routes.bp)
    app.register_blueprint(auth.bp)

    @app.cli.command("init-db")
    def init_db():
        from app import models  # noqa: F401
        db.create_all()
        print("Database initialized.")

    @app.cli.command("seed")
    def seed():
        from app.models import Player
        defaults = [
            ("Queso", "Marcos"),
            ("Ghiro", "Ghiro"),
            ("Ando", "Ando"),
            ("Pyrook", "Nacho"),
            ("Tompson", "Tompson"),
            ("Lommi", "Lommi"),
            ("Feri", "Federico"),
            ("Pancho", "Pancho"),
            ("Marqui", "Marcos"),
            ("Juani", "Juani"),
            ("Lucho", "Lucho"),
        ]
        added = 0
        for nickname, nombre_real in defaults:
            if not Player.query.filter_by(nickname=nickname).first():
                db.session.add(Player(nickname=nickname, nombre_real=nombre_real))
                added += 1
        db.session.commit()
        print(f"Seeded {added} new player(s) (skipped existing).")

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
        from app.models import Player
        p = Player.query.filter_by(nickname=nickname).first()
        if not p:
            print(f"Player '{nickname}' no encontrado.")
            return
        p.set_password(password)
        p.must_change_password = True
        db.session.commit()
        print(f"Password seteada para '{nickname}' (debe cambiarla en el primer login).")

    @app.cli.command("init-passwords")
    def init_passwords():
        """Genera passwords random para todos los players sin password seteada."""
        from app.models import Player
        rows = Player.query.order_by(Player.id).all()
        print()
        print(f"{'Nickname':<12} {'Nombre':<18} Password inicial")
        print("-" * 60)
        for p in rows:
            if p.password_hash:
                print(f"{p.nickname:<12} {p.nombre_real or '-':<18} (ya tiene password)")
                continue
            pw = secrets.token_urlsafe(6)
            p.set_password(pw)
            p.must_change_password = True
            print(f"{p.nickname:<12} {p.nombre_real or '-':<18} {pw}")
        db.session.commit()
        print()
        print("Compartir estas passwords con cada player. Las van a tener que cambiar al primer login.")

    return app
