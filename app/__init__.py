import click
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData

db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    db.init_app(app)

    from app import routes
    app.register_blueprint(routes.bp)

    @app.cli.command("init-db")
    def init_db():
        from app import models  # noqa: F401
        db.create_all()
        print("Database initialized.")

    @app.cli.command("seed")
    def seed():
        from app.models import Player
        # nickname, nombre_real
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

    return app
