import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    current_app, send_from_directory, abort,
)
from flask_login import login_required, current_user
from app import db
from app.models import Usuario, Report, ReportReviewer, ReportAttachment, Vote, Punto, Comment

TOTAL_YES_THRESHOLD = 6

bp = Blueprint("reports", __name__, url_prefix="/reports")

ALLOWED_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "pdf"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_FILES = 3


def _ext(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""


def _eligible_players(exclude_ids=()):
    """Players elegibles (rol=player), excluyendo los IDs dados."""
    q = Usuario.query.filter(Usuario.rol == "player")
    if exclude_ids:
        q = q.filter(~Usuario.id.in_(exclude_ids))
    return q.order_by(Usuario.nickname).all()


@bp.route("/")
@login_required
def list_reports():
    return redirect(url_for("reports.active_reports"))


@bp.route("/active")
@login_required
def active_reports():
    reports = (
        Report.query.filter(Report.status == "pending")
        .order_by(Report.created_at.desc())
        .all()
    )
    return render_template("reports/list.html", reports=reports, current="active",
                           empty_msg="No hay reportes activos.")


@bp.route("/pending")
@login_required
def pending_reports():
    """Reportes activos donde el usuario fue asignado como reviewer."""
    reports = (
        Report.query
        .join(ReportReviewer, ReportReviewer.report_id == Report.id)
        .filter(ReportReviewer.usuario_id == current_user.id)
        .filter(Report.status == "pending")
        .order_by(Report.created_at.desc())
        .all()
    )
    return render_template(
        "reports/list.html",
        reports=reports,
        current="pending",
        empty_msg="No tenes reportes pendientes para revisar.",
    )


@bp.route("/closed")
@login_required
def closed_reports():
    reports = (
        Report.query.filter(Report.status.in_(["approved", "rejected", "cancelled"]))
        .order_by(Report.created_at.desc())
        .all()
    )
    return render_template("reports/list.html", reports=reports, current="closed",
                           empty_msg="No hay reportes cerrados todavia.")


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_report():
    targets = _eligible_players(exclude_ids=[current_user.id])

    if request.method == "POST":
        target_id = request.form.get("target_id", type=int)
        points = request.form.get("points", type=int)
        description = (request.form.get("description") or "").strip()
        evidence_text = (request.form.get("evidence_text") or "").strip() or None
        reviewer_ids = [int(x) for x in request.form.getlist("reviewers") if x.isdigit()]
        files = [f for f in request.files.getlist("files") if f and f.filename]

        if not target_id or target_id == current_user.id:
            flash("Elegi un target valido (no podes ser vos mismo).", "error")
            return redirect(url_for("reports.new_report"))

        target = Usuario.query.get(target_id)
        if not target or target.rol != "player":
            flash("Target invalido.", "error")
            return redirect(url_for("reports.new_report"))

        if not points or points < 1 or points > 10:
            flash("Los puntos tienen que estar entre 1 y 10.", "error")
            return redirect(url_for("reports.new_report"))

        if not description or len(description) < 5:
            flash("Escribi una descripcion (al menos 5 caracteres).", "error")
            return redirect(url_for("reports.new_report"))

        # Reviewer validation: excluir reporter y target del input; minimo 2.
        invalid = {current_user.id, target_id}
        clean_reviewer_ids = [rid for rid in reviewer_ids if rid not in invalid]
        clean_reviewer_ids = list(dict.fromkeys(clean_reviewer_ids))  # dedup conservando orden

        if len(clean_reviewer_ids) < 2:
            flash("Elegi al menos 2 reviewers (no podes ser vos ni el target).", "error")
            return redirect(url_for("reports.new_report"))

        # File validation
        if len(files) > MAX_FILES:
            flash(f"Maximo {MAX_FILES} archivos.", "error")
            return redirect(url_for("reports.new_report"))
        for f in files:
            if _ext(f.filename) not in ALLOWED_EXTS:
                flash(f"Tipo no permitido: {f.filename}. Solo: {', '.join(sorted(ALLOWED_EXTS))}", "error")
                return redirect(url_for("reports.new_report"))

        # Crear reporte
        rep = Report(
            reporter_id=current_user.id,
            target_id=target_id,
            points=points,
            description=description,
            evidence_text=evidence_text,
            status="pending",
        )
        db.session.add(rep)
        db.session.flush()

        for rid in clean_reviewer_ids:
            db.session.add(ReportReviewer(report_id=rep.id, usuario_id=rid))

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
            db.session.add(ReportAttachment(
                report_id=rep.id,
                filename=stored,
                original_name=secure_filename(f.filename),
                mime_type=(f.mimetype or "application/octet-stream")[:80],
                size_bytes=size,
            ))

        db.session.commit()
        flash(f"Reporte #{rep.id} creado.", "success")
        return redirect(url_for("reports.detail", report_id=rep.id))

    return render_template(
        "reports/new.html",
        targets=targets,
        reviewers_pool=targets,  # mismo pool: players != yo (target tambien se filtra al elegir)
        max_files=MAX_FILES,
        max_size_mb=MAX_FILE_SIZE // (1024 * 1024),
        allowed_exts=sorted(ALLOWED_EXTS),
    )


@bp.route("/<int:report_id>")
@login_required
def detail(report_id):
    rep = Report.query.get_or_404(report_id)

    yes_voter_ids = {v.usuario_id for v in rep.votes if v.vote == "yes"}
    reviewer_ids = {r.usuario_id for r in rep.reviewers}

    progress = {
        "yes_count": len(yes_voter_ids),
        "no_count": sum(1 for v in rep.votes if v.vote == "no"),
        "reviewers_yes": len(reviewer_ids & yes_voter_ids),
        "total_reviewers": len(reviewer_ids),
        "total_yes_threshold": TOTAL_YES_THRESHOLD,
    }

    my_vote = next((v for v in rep.votes if v.usuario_id == current_user.id), None)
    can_vote = (
        rep.status == "pending"
        and current_user.id != rep.reporter_id
        and current_user.id != rep.target_id
    )
    cant_vote_reason = None
    if not can_vote:
        if rep.status != "pending":
            cant_vote_reason = f"El reporte esta {rep.status}, ya no se puede votar."
        elif current_user.id == rep.reporter_id:
            cant_vote_reason = "Sos el que creaste este reporte, no podes votar."
        elif current_user.id == rep.target_id:
            cant_vote_reason = "Sos el target del reporte, no podes votar."

    # Build comments tree (self-referential)
    all_comments = (
        Comment.query.filter(Comment.report_id == rep.id)
        .order_by(Comment.created_at)
        .all()
    )
    children_by_parent = {}
    for c in all_comments:
        children_by_parent.setdefault(c.parent_id, []).append(c)
    top_level_comments = children_by_parent.get(None, [])

    return render_template(
        "reports/detail.html",
        report=rep,
        progress=progress,
        my_vote=my_vote,
        can_vote=can_vote,
        cant_vote_reason=cant_vote_reason,
        top_level_comments=top_level_comments,
        children_by_parent=children_by_parent,
        total_comments=len(all_comments),
    )


@bp.route("/<int:report_id>/comment", methods=["POST"])
@login_required
def comment(report_id):
    rep = Report.query.get_or_404(report_id)

    body = (request.form.get("body") or "").strip()
    parent_id_raw = request.form.get("parent_id")
    parent_id = int(parent_id_raw) if parent_id_raw and parent_id_raw.isdigit() else None

    if not body:
        flash("El comentario no puede estar vacio.", "error")
        return redirect(url_for("reports.detail", report_id=rep.id))

    if parent_id:
        parent = Comment.query.get(parent_id)
        if not parent or parent.report_id != rep.id:
            abort(400)

    new_c = Comment(
        report_id=rep.id,
        usuario_id=current_user.id,
        parent_id=parent_id,
        body=body[:5000],
    )
    db.session.add(new_c)
    db.session.commit()

    return redirect(
        url_for("reports.detail", report_id=rep.id) + f"#comment-{new_c.id}"
    )


@bp.route("/<int:report_id>/vote", methods=["POST"])
@login_required
def vote(report_id):
    rep = Report.query.get_or_404(report_id)

    if rep.status != "pending":
        flash("El reporte ya esta cerrado.", "error")
        return redirect(url_for("reports.detail", report_id=rep.id))
    if current_user.id in (rep.reporter_id, rep.target_id):
        flash("No podes votar en este reporte (sos reporter o target).", "error")
        return redirect(url_for("reports.detail", report_id=rep.id))

    choice = request.form.get("vote")
    comment = (request.form.get("comment") or "").strip() or None
    if choice not in ("yes", "no"):
        flash("Voto invalido.", "error")
        return redirect(url_for("reports.detail", report_id=rep.id))

    existing = Vote.query.filter_by(report_id=rep.id, usuario_id=current_user.id).first()
    if existing:
        flash("Ya votaste en este reporte. El voto no se puede cambiar.", "error")
        return redirect(url_for("reports.detail", report_id=rep.id))

    db.session.add(Vote(
        report_id=rep.id,
        usuario_id=current_user.id,
        vote=choice,
        comment=comment,
    ))
    db.session.commit()

    reason = _check_and_apply_approval(rep)
    if reason:
        flash(
            f"Voto registrado. Reporte aprobado ({reason}). "
            f"Se aplicaron {rep.points} puntos a {rep.target.nickname}.",
            "success",
        )
    else:
        flash("Voto registrado.", "success")

    return redirect(url_for("reports.detail", report_id=rep.id))


def _check_and_apply_approval(rep):
    """Si se cumple alguna condicion de aprobacion, marca approved y suma Puntos.
    Devuelve string con el motivo si aprobo, None si no."""
    if rep.status != "pending":
        return None

    yes_voter_ids = {
        row[0] for row in db.session.query(Vote.usuario_id)
        .filter(Vote.report_id == rep.id, Vote.vote == "yes").all()
    }
    reviewer_ids = {
        row[0] for row in db.session.query(ReportReviewer.usuario_id)
        .filter(ReportReviewer.report_id == rep.id).all()
    }

    if reviewer_ids and reviewer_ids.issubset(yes_voter_ids):
        _apply_approval(rep)
        return "todos los reviewers votaron si"

    if len(yes_voter_ids) >= TOTAL_YES_THRESHOLD:
        _apply_approval(rep)
        return f"{len(yes_voter_ids)} players votaron si"

    return None


def _apply_approval(rep):
    rep.status = "approved"
    db.session.add(Punto(player_id=rep.target_id, points=rep.points))
    db.session.commit()


@bp.route("/uploads/<filename>")
@login_required
def serve_upload(filename):
    if "/" in filename or "\\" in filename or ".." in filename:
        abort(404)
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    return send_from_directory(upload_dir, filename)
