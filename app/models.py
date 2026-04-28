from datetime import datetime
from app import db


class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    reports = db.relationship("LagReport", backref="player", lazy=True, cascade="all, delete-orphan")


class LagReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    lag_ms = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(255))
    reported_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
