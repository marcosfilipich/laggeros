import click
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

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
        defaults_players = ["Marcos", "Capo1", "Capo2"]
        for name in defaults_players:
            if not Player.query.filter_by(name=name).first():
                db.session.add(Player(name=name))
        db.session.commit()
        print("Seeded default players.")

    @app.cli.command("reset-db")
    @click.confirmation_option(prompt="Esto borra TODAS las tablas y datos. Seguro?")
    def reset_db():
        from app import models  # noqa: F401
        db.drop_all()
        db.create_all()
        print("Database reset (all tables dropped and recreated).")

    return app
