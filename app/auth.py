from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import Player

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        nickname = (request.form.get("nickname") or "").strip()
        password = request.form.get("password") or ""

        player = Player.query.filter_by(nickname=nickname).first()
        if not player or not player.check_password(password):
            flash("Nickname o password incorrectos.", "error")
            return redirect(url_for("auth.login"))

        login_user(player, remember=True)
        if player.must_change_password:
            return redirect(url_for("auth.change_password"))

        next_url = request.args.get("next")
        return redirect(next_url or url_for("main.index"))

    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesion cerrada.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password") or ""
        new_pw = request.form.get("new_password") or ""
        confirm_pw = request.form.get("confirm_password") or ""

        if not current_user.check_password(current_pw):
            flash("Password actual incorrecta.", "error")
            return redirect(url_for("auth.change_password"))

        if len(new_pw) < 6:
            flash("La nueva password tiene que tener al menos 6 caracteres.", "error")
            return redirect(url_for("auth.change_password"))

        if new_pw != confirm_pw:
            flash("Las passwords no coinciden.", "error")
            return redirect(url_for("auth.change_password"))

        current_user.set_password(new_pw)
        current_user.must_change_password = False
        db.session.commit()
        flash("Password actualizada.", "success")
        return redirect(url_for("main.index"))

    return render_template("auth/change_password.html", forced=current_user.must_change_password)
