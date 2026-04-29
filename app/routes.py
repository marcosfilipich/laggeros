from datetime import datetime
from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func
from app import db
from app.models import Usuario, Punto

bp = Blueprint("main", __name__)

BLUE_STREAK_DAYS = 10           # dias minimos sin laggearla para fueguito azul
RED_STREAK_GAP_SECONDS = 48 * 3600  # max gap entre lags consecutivos para que cuenten como racha


def _compute_streak(puntos, now):
    """puntos: list ordenada asc por date_inserted, todos del mismo player.
    Returns dict con eventuales 'blue_days' y 'red_days'."""
    info = {}
    if not puntos:
        return info

    last = puntos[-1].date_inserted
    days_since_last = (now - last).days
    if days_since_last >= BLUE_STREAK_DAYS:
        info["blue_days"] = days_since_last

    if len(puntos) >= 2:
        i = len(puntos) - 1
        while i > 0 and (puntos[i].date_inserted - puntos[i - 1].date_inserted).total_seconds() <= RED_STREAK_GAP_SECONDS:
            i -= 1
        streak = puntos[i:]
        active = (now - last).total_seconds() <= RED_STREAK_GAP_SECONDS
        if len(streak) >= 2 and active:
            info["red_days"] = (last - streak[0].date_inserted).days

    return info


@bp.route("/")
@login_required
def index():
    ranking = (
        db.session.query(
            Usuario.id,
            Usuario.nickname,
            Usuario.nombre_real,
            func.coalesce(func.sum(Punto.points), 0).label("total_points"),
            func.count(Punto.id).label("report_count"),
            func.max(Punto.date_inserted).label("last_report"),
        )
        .outerjoin(Punto, Punto.player_id == Usuario.id)
        .filter(Usuario.rol == "player")
        .group_by(Usuario.id, Usuario.nickname, Usuario.nombre_real)
        .order_by(func.coalesce(func.sum(Punto.points), 0).desc())
        .all()
    )

    # Rachas: cargo todos los puntos y agrupo por player en Python
    now = datetime.utcnow()
    puntos_by_player = {}
    for p in Punto.query.order_by(Punto.player_id, Punto.date_inserted).all():
        puntos_by_player.setdefault(p.player_id, []).append(p)
    streaks = {pid: _compute_streak(plist, now) for pid, plist in puntos_by_player.items()}

    return render_template("index.html", ranking=ranking, streaks=streaks)


@bp.route("/history")
@login_required
def history():
    reports = Punto.query.order_by(Punto.date_inserted.desc()).limit(100).all()
    return render_template("history.html", reports=reports)
