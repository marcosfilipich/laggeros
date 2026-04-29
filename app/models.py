from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class Usuario(db.Model, UserMixin):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(80), unique=True, nullable=False)
    nombre_real = db.Column(db.String(120), nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=True)
    rol = db.Column(db.String(20), nullable=False, default="player")

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
    player_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    date_inserted = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    target_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=False)
    evidence_text = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    reporter = db.relationship("Usuario", foreign_keys=[reporter_id])
    target = db.relationship("Usuario", foreign_keys=[target_id])

    reviewers = db.relationship(
        "ReportReviewer", backref="report", cascade="all, delete-orphan", lazy=True
    )
    attachments = db.relationship(
        "ReportAttachment", backref="report", cascade="all, delete-orphan", lazy=True
    )
    votes = db.relationship(
        "Vote", backref="report", cascade="all, delete-orphan", lazy=True
    )


class ReportReviewer(db.Model):
    __tablename__ = "report_reviewers"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)

    usuario = db.relationship("Usuario")

    __table_args__ = (db.UniqueConstraint("report_id", "usuario_id", name="uq_report_reviewer"),)


class ReportAttachment(db.Model):
    __tablename__ = "report_attachments"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(80), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Vote(db.Model):
    __tablename__ = "votes"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    vote = db.Column(db.String(10), nullable=False)
    comment = db.Column(db.Text, nullable=True)
    voted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    usuario = db.relationship("Usuario")

    __table_args__ = (db.UniqueConstraint("report_id", "usuario_id", name="uq_vote"),)


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("comments.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    usuario = db.relationship("Usuario")
    report = db.relationship("Report", backref=db.backref("comments", lazy=True, cascade="all, delete-orphan"))
    parent = db.relationship("Comment", remote_side=[id], backref="children")
