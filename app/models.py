from datetime import datetime
from app import db


class Player(db.Model):
    __tablename__ = "players"

    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(80), unique=True, nullable=False)
    nombre_real = db.Column(db.String(120), nullable=True)

    puntos = db.relationship(
        "Punto", backref="player", lazy=True, cascade="all, delete-orphan"
    )


class Punto(db.Model):
    __tablename__ = "puntos"

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    date_inserted = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
