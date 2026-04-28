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
        from app.models import Player, Game
        defaults_players = ["Marcos", "Capo1", "Capo2"]
        defaults_games = ["CS2", "Valorant", "League of Legends", "Fortnite"]
        for name in defaults_players:
            if not Player.query.filter_by(name=name).first():
                db.session.add(Player(name=name))
        for name in defaults_games:
            if not Game.query.filter_by(name=name).first():
                db.session.add(Game(name=name))
        db.session.commit()
        print("Seeded default players and games.")

    return app
