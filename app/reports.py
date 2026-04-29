import os
import uuid
from werkzeug.utils import secure_filename
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    current_app, send_from_directory, abort,
)
from flask_login import login_required, current_user
from app import db
from app.models import Usuario, Report, ReportReviewer, ReportAttachment

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
    return render_template("reports/detail.html", report=rep)


@bp.route("/uploads/<filename>")
@login_required
def serve_upload(filename):
    if "/" in filename or "\\" in filename or ".." in filename:
        abort(404)
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    return send_from_directory(upload_dir, filename)
