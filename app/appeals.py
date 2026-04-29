import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, abort,
    current_app, send_from_directory,
)
from flask_login import login_required, current_user
from app import db
from app.models import Usuario, Report, Vote, Punto, Appeal, AppealVote, AppealAttachment

bp = Blueprint("appeals", __name__, url_prefix="/appeals")

APPEAL_YES_THRESHOLD = 5            # >= 5 votos SI -> approved
APPEAL_NO_THRESHOLD = 3             # >= 3 votos NO -> rejected (con 12 players ya no dan los numeros)
APPEAL_REJECTION_PENALTY = 3        # puntos para el apelante si pierde la apelacion
APPEAL_APPROVAL_BONUS = 1           # punto extra a favor del apelante si gana

ALLOWED_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "pdf"}
MAX_FILE_SIZE = 5 * 1024 * 1024     # 5MB
MAX_FILES = 3


def _ext(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""


def _eligible_reports_for_appeal(user_id):
    """Reportes que el user puede apelar:
       - target_id = user
       - status = approved
       - exactamente 2 votos SI en total (flujo de aprobacion via reviewers)
       - sin Appeal previo
    """
    existing_appeal_subq = db.session.query(Appeal.report_id)
    candidates = (
        Report.query
        .filter(Report.target_id == user_id)
        .filter(Report.status == "approved")
        .filter(~Report.id.in_(existing_appeal_subq))
        .all()
    )
    eligible = []
    for r in candidates:
        yes_count = sum(1 for v in r.votes if v.vote == "yes")
        if yes_count == 2:
            eligible.append(r)
    return eligible


def _appeal_voting_excluded_users(appeal):
    """IDs de usuarios que no pueden votar en esta apelacion."""
    excluded = {appeal.appealer_id, appeal.report.reporter_id}
    yes_voter_ids = {v.usuario_id for v in appeal.report.votes if v.vote == "yes"}
    return excluded | yes_voter_ids


@bp.route("/")
@login_required
def list_appeals_redirect():
    return redirect(url_for("appeals.list_appeals"))


@bp.route("/list")
@login_required
def list_appeals():
    appeals = Appeal.query.order_by(Appeal.created_at.desc()).all()
    return render_template("appeals/list.html", appeals=appeals, current="list",
                           empty_msg="Todavia no hay apelaciones.")


@bp.route("/pending")
@login_required
def pending_appeals():
    """Apelaciones pending donde current_user puede votar y todavia no voto."""
    appeals_q = Appeal.query.filter(Appeal.status == "pending").all()
    eligible = []
    for a in appeals_q:
        if current_user.id in _appeal_voting_excluded_users(a):
            continue
        if AppealVote.query.filter_by(appeal_id=a.id, usuario_id=current_user.id).first():
            continue
        eligible.append(a)
    return render_template("appeals/list.html", appeals=eligible, current="pending",
                           empty_msg="No tenes apelaciones pendientes para votar.")


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_appeal():
    eligible = _eligible_reports_for_appeal(current_user.id)

    if request.method == "POST":
        report_id = request.form.get("report_id", type=int)
        description = (request.form.get("description") or "").strip()
        files = [f for f in request.files.getlist("files") if f and f.filename]

        if not report_id:
            flash("Elegi un reporte para apelar.", "error")
            return redirect(url_for("appeals.new_appeal"))

        if not description or len(description) < 5:
            flash("Escribi una descripcion explicando por que apelas (min 5 chars).", "error")
            return redirect(url_for("appeals.new_appeal"))

        rep = Report.query.get(report_id)
        if not rep or rep.id not in {r.id for r in eligible}:
            flash("Ese reporte no es apelable.", "error")
            return redirect(url_for("appeals.new_appeal"))

        if len(files) > MAX_FILES:
            flash(f"Maximo {MAX_FILES} archivos.", "error")
            return redirect(url_for("appeals.new_appeal"))
        for f in files:
            if _ext(f.filename) not in ALLOWED_EXTS:
                flash(f"Tipo no permitido: {f.filename}. Solo: {', '.join(sorted(ALLOWED_EXTS))}", "error")
                return redirect(url_for("appeals.new_appeal"))

        appeal = Appeal(
            report_id=rep.id,
            appealer_id=current_user.id,
            description=description,
            status="pending",
        )
        db.session.add(appeal)
        db.session.flush()

        upload_dir = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_dir, exist_ok=True)
        for f in files:
            ext = _ext(f.filename)
            stored = f"{uuid.uuid4().hex}.{ext}"
            path = os.path.join(upload_dir, stored)
            f.save(path)
            size = os.path.getsize(path)
            if size > MAX_FILE_SIZE:
                os.remove(path)
                flash(f"Archivo {f.filename} supera 5MB - no guardado.", "error")
                continue
            db.session.add(AppealAttachment(
                appeal_id=appeal.id,
                filename=stored,
                original_name=secure_filename(f.filename),
                mime_type=(f.mimetype or "application/octet-stream")[:80],
                size_bytes=size,
            ))

        db.session.commit()
        flash(f"Apelacion #{appeal.id} creada.", "success")
        return redirect(url_for("appeals.detail", appeal_id=appeal.id))

    return render_template(
        "appeals/new.html",
        eligible=eligible,
        current="new",
        max_files=MAX_FILES,
        max_size_mb=MAX_FILE_SIZE // (1024 * 1024),
        allowed_exts=sorted(ALLOWED_EXTS),
    )


@bp.route("/uploads/<filename>")
@login_required
def serve_upload(filename):
    if "/" in filename or "\\" in filename or ".." in filename:
        abort(404)
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    return send_from_directory(upload_dir, filename)


@bp.route("/<int:appeal_id>")
@login_required
def detail(appeal_id):
    appeal = Appeal.query.get_or_404(appeal_id)

    yes_count = sum(1 for v in appeal.votes if v.vote == "yes")
    no_count = sum(1 for v in appeal.votes if v.vote == "no")
    progress = {
        "yes_count": yes_count,
        "no_count": no_count,
        "yes_threshold": APPEAL_YES_THRESHOLD,
        "no_threshold": APPEAL_NO_THRESHOLD,
    }

    excluded = _appeal_voting_excluded_users(appeal)
    my_vote = next((v for v in appeal.votes if v.usuario_id == current_user.id), None)
    can_vote = (
        appeal.status == "pending"
        and current_user.id not in excluded
    )
    cant_vote_reason = None
    if not can_vote and not my_vote:
        if appeal.status != "pending":
            cant_vote_reason = f"La apelacion esta {appeal.status}, ya no se vota."
        elif current_user.id == appeal.appealer_id:
            cant_vote_reason = "Sos el apelante, no podes votar tu propia apelacion."
        elif current_user.id == appeal.report.reporter_id:
            cant_vote_reason = "Sos el reporter del reclamo original, no podes votar."
        else:
            cant_vote_reason = "Votaste SI en el reclamo original, no podes votar la apelacion."

    # Lista de SI-voters originales para mostrar en la pagina de detalle
    original_yes_voters = [v.usuario for v in appeal.report.votes if v.vote == "yes"]

    return render_template(
        "appeals/detail.html",
        appeal=appeal,
        progress=progress,
        my_vote=my_vote,
        can_vote=can_vote,
        cant_vote_reason=cant_vote_reason,
        original_yes_voters=original_yes_voters,
    )


@bp.route("/<int:appeal_id>/vote", methods=["POST"])
@login_required
def vote(appeal_id):
    appeal = Appeal.query.get_or_404(appeal_id)

    if appeal.status != "pending":
        flash("La apelacion ya esta cerrada.", "error")
        return redirect(url_for("appeals.detail", appeal_id=appeal.id))

    excluded = _appeal_voting_excluded_users(appeal)
    if current_user.id in excluded:
        flash("No podes votar en esta apelacion.", "error")
        return redirect(url_for("appeals.detail", appeal_id=appeal.id))

    choice = request.form.get("vote")
    comment = (request.form.get("comment") or "").strip() or None
    if choice not in ("yes", "no"):
        flash("Voto invalido.", "error")
        return redirect(url_for("appeals.detail", appeal_id=appeal.id))

    existing = AppealVote.query.filter_by(appeal_id=appeal.id, usuario_id=current_user.id).first()
    if existing:
        flash("Ya votaste en esta apelacion. El voto no se puede cambiar.", "error")
        return redirect(url_for("appeals.detail", appeal_id=appeal.id))

    db.session.add(AppealVote(
        appeal_id=appeal.id,
        usuario_id=current_user.id,
        vote=choice,
        comment=comment,
    ))
    db.session.commit()

    decision = _check_and_apply_appeal_decision(appeal)
    if decision and decision["status"] == "approved":
        flash(
            f"Voto registrado. Apelacion APROBADA. Se revirtieron los {appeal.report.points} puntos del reclamo original "
            f"+ 1 punto extra a favor de {appeal.appealer.nickname} por ataque injusto.",
            "success",
        )
    elif decision and decision["status"] == "rejected":
        flash(
            f"Voto registrado. Apelacion RECHAZADA. {appeal.appealer.nickname} suma {APPEAL_REJECTION_PENALTY} puntos "
            f"por apelar sin razon.",
            "success",
        )
    else:
        flash("Voto registrado.", "success")

    return redirect(url_for("appeals.detail", appeal_id=appeal.id))


def _check_and_apply_appeal_decision(appeal):
    """Si se cumple alguna condicion, marca status, registra resolved_at,
    y aplica el outcome (Punto al apelante). Devuelve dict {status} o None."""
    if appeal.status != "pending":
        return None

    yes_count = AppealVote.query.filter_by(appeal_id=appeal.id, vote="yes").count()
    no_count = AppealVote.query.filter_by(appeal_id=appeal.id, vote="no").count()

    if yes_count >= APPEAL_YES_THRESHOLD:
        appeal.status = "approved"
        appeal.resolved_at = datetime.utcnow()
        # Revertir los puntos del reporte original + 1 a favor (negativo = beneficio)
        revert = -(appeal.report.points + APPEAL_APPROVAL_BONUS)
        db.session.add(Punto(
            player_id=appeal.appealer_id,
            points=revert,
            motivo=Punto.MOTIVO_APPEAL_APPROVED,
        ))
        db.session.commit()
        return {"status": "approved"}

    if no_count >= APPEAL_NO_THRESHOLD:
        appeal.status = "rejected"
        appeal.resolved_at = datetime.utcnow()
        db.session.add(Punto(
            player_id=appeal.appealer_id,
            points=APPEAL_REJECTION_PENALTY,
            motivo=Punto.MOTIVO_APPEAL_REJECTED,
        ))
        db.session.commit()
        return {"status": "rejected"}

    return None
