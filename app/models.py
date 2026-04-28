from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class Player(db.Model, UserMixin):
    __tablename__ = "players"

    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(80), unique=True, nullable=False)
    nombre_real = db.Column(db.String(120), nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=True)

    puntos = db.relationship(
        "Punto", backref="player", lazy=True, cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)


class Punto(db.Model):
    __tablename__ = "puntos"

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    date_inserted = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
