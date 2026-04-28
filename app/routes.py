from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import func
from app import db
from app.models import Player, Punto

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    ranking = (
        db.session.query(
            Player.id,
            Player.nickname,
            Player.nombre_real,
            func.coalesce(func.sum(Punto.points), 0).label("total_points"),
            func.count(Punto.id).label("report_count"),
            func.max(Punto.date_inserted).label("last_report"),
        )
        .outerjoin(Punto, Punto.player_id == Player.id)
        .group_by(Player.id, Player.nickname, Player.nombre_real)
        .order_by(func.coalesce(func.sum(Punto.points), 0).desc())
        .all()
    )
    return render_template("index.html", ranking=ranking)


@bp.route("/manage", methods=["GET", "POST"])
@login_required
def manage():
    if request.method == "POST":
        nickname = (request.form.get("nickname") or "").strip()
        nombre_real = (request.form.get("nombre_real") or "").strip() or None

        if not nickname:
            flash("Nickname vacio.", "error")
        elif Player.query.filter_by(nickname=nickname).first():
            flash(f"Player '{nickname}' ya existe.", "error")
        else:
            db.session.add(Player(nickname=nickname, nombre_real=nombre_real))
            db.session.commit()
            flash(f"Player '{nickname}' agregado.", "success")
        return redirect(url_for("main.manage"))

    players = Player.query.order_by(Player.nickname).all()
    return render_template("manage.html", players=players)


@bp.route("/history")
@login_required
def history():
    reports = Punto.query.order_by(Punto.date_inserted.desc()).limit(100).all()
    return render_template("history.html", reports=reports)
