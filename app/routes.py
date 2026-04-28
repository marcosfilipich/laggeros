from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import func
from app import db
from app.models import Player, Game, LagReport

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    game_id = request.args.get("game_id", type=int)

    query = (
        db.session.query(
            Player.id,
            Player.name,
            func.avg(LagReport.lag_ms).label("avg_lag"),
            func.max(LagReport.lag_ms).label("max_lag"),
            func.count(LagReport.id).label("report_count"),
        )
        .join(LagReport, LagReport.player_id == Player.id)
    )
    if game_id:
        query = query.filter(LagReport.game_id == game_id)

    ranking = (
        query.group_by(Player.id, Player.name)
        .order_by(func.avg(LagReport.lag_ms).desc())
        .all()
    )

    games = Game.query.order_by(Game.name).all()
    selected_game = Game.query.get(game_id) if game_id else None

    return render_template(
        "index.html",
        ranking=ranking,
        games=games,
        selected_game=selected_game,
    )


@bp.route("/report", methods=["GET", "POST"])
def report():
    if request.method == "POST":
        player_id = request.form.get("player_id", type=int)
        game_id = request.form.get("game_id", type=int)
        lag_ms = request.form.get("lag_ms", type=int)
        note = (request.form.get("note") or "").strip() or None

        if not (player_id and game_id and lag_ms is not None and lag_ms >= 0):
            flash("Datos invalidos. Revisa los campos.", "error")
            return redirect(url_for("main.report"))

        db.session.add(
            LagReport(player_id=player_id, game_id=game_id, lag_ms=lag_ms, note=note)
        )
        db.session.commit()
        flash("Reporte de lag agregado.", "success")
        return redirect(url_for("main.index"))

    players = Player.query.order_by(Player.name).all()
    games = Game.query.order_by(Game.name).all()
    return render_template("report.html", players=players, games=games)


@bp.route("/manage", methods=["GET", "POST"])
def manage():
    if request.method == "POST":
        kind = request.form.get("kind")
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Nombre vacio.", "error")
        elif kind == "player":
            if Player.query.filter_by(name=name).first():
                flash(f"Player '{name}' ya existe.", "error")
            else:
                db.session.add(Player(name=name))
                db.session.commit()
                flash(f"Player '{name}' agregado.", "success")
        elif kind == "game":
            if Game.query.filter_by(name=name).first():
                flash(f"Game '{name}' ya existe.", "error")
            else:
                db.session.add(Game(name=name))
                db.session.commit()
                flash(f"Game '{name}' agregado.", "success")
        return redirect(url_for("main.manage"))

    players = Player.query.order_by(Player.name).all()
    games = Game.query.order_by(Game.name).all()
    return render_template("manage.html", players=players, games=games)


@bp.route("/history")
def history():
    reports = (
        LagReport.query.order_by(LagReport.reported_at.desc()).limit(100).all()
    )
    return render_template("history.html", reports=reports)
