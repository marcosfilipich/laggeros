from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import Usuario

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _require_admin():
    if not current_user.is_authenticated or current_user.rol != "admin":
        abort(403)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        nickname = (request.form.get("nickname") or "").strip()
        password = request.form.get("password") or ""

        usuario = Usuario.query.filter_by(nickname=nickname).first()
        if not usuario or not usuario.check_password(password):
            flash("Nickname o password incorrectos.", "error")
            return redirect(url_for("auth.login"))

        if usuario.rol == "pending_observer":
            flash("Tu cuenta esta pendiente de aprobacion del admin. Te avisamos cuando este lista.", "error")
            return redirect(url_for("auth.login"))

        login_user(usuario, remember=True)
        if usuario.must_change_password:
            return redirect(url_for("auth.change_password"))

        next_url = request.args.get("next")
        return redirect(next_url or url_for("main.index"))

    return render_template("auth/login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        nickname = (request.form.get("nickname") or "").strip()
        nombre_real = (request.form.get("nombre_real") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        if not nickname or len(nickname) < 2 or len(nickname) > 80:
            flash("Nickname invalido (2 a 80 chars).", "error")
            return redirect(url_for("auth.register"))

        if Usuario.query.filter_by(nickname=nickname).first():
            flash("Ese nickname ya esta tomado.", "error")
            return redirect(url_for("auth.register"))

        if not nombre_real or len(nombre_real) > 120:
            flash("Escribi un nombre real (max 120 chars).", "error")
            return redirect(url_for("auth.register"))

        if len(password) < 6:
            flash("La password tiene que tener al menos 6 caracteres.", "error")
            return redirect(url_for("auth.register"))

        if password != confirm:
            flash("Las passwords no coinciden.", "error")
            return redirect(url_for("auth.register"))

        u = Usuario(
            nickname=nickname,
            nombre_real=nombre_real,
            rol="pending_observer",
            must_change_password=False,
            has_seen_about=False,
        )
        u.set_password(password)
        db.session.add(u)
        db.session.commit()

        flash(
            "Cuenta creada. Queda pendiente de aprobacion del admin. "
            "Cuando te aprueben vas a poder entrar con esas credenciales.",
            "success",
        )
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesion cerrada.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    forced = current_user.must_change_password

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
        return redirect(url_for("auth.change_password"))

    template = "auth/change_password_forced.html" if forced else "auth/change_password.html"
    return render_template(template)


@bp.route("/admin/pending")
@login_required
def admin_pending():
    _require_admin()
    pending = (
        Usuario.query.filter(Usuario.rol == "pending_observer")
        .order_by(Usuario.id)
        .all()
    )
    return render_template("auth/admin_pending.html", pending=pending)


@bp.route("/admin/pending/<int:user_id>/approve", methods=["POST"])
@login_required
def admin_approve(user_id):
    _require_admin()
    u = Usuario.query.get_or_404(user_id)
    if u.rol != "pending_observer":
        flash("Ese usuario no esta pendiente.", "error")
        return redirect(url_for("auth.admin_pending"))
    u.rol = "observer"
    db.session.commit()
    flash(f"{u.nickname} aprobado como observer.", "success")
    return redirect(url_for("auth.admin_pending"))


@bp.route("/admin/pending/<int:user_id>/reject", methods=["POST"])
@login_required
def admin_reject(user_id):
    _require_admin()
    u = Usuario.query.get_or_404(user_id)
    if u.rol != "pending_observer":
        flash("Ese usuario no esta pendiente.", "error")
        return redirect(url_for("auth.admin_pending"))
    nick = u.nickname
    db.session.delete(u)
    db.session.commit()
    flash(f"Solicitud de {nick} rechazada y borrada.", "success")
    return redirect(url_for("auth.admin_pending"))
