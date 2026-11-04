"""Appointment booking, editing, cancellation and status workflow."""

from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Appointment, LoyaltyCard, Service, Specialist, User
from ..utils import (
    CLOSING_TIME,
    OPENING_TIME,
    has_conflict,
    validate_business_hours,
)
from ..validators import (
    parse_date_field,
    parse_time_field,
    validate_optional,
)

bp = Blueprint("appointments", __name__, url_prefix="/appointments")

VALID_STATUSES = ("pendiente", "confirmada", "cancelada", "completada")


def _admin(user=None):
    user = user or current_user
    return user.role is not None and (user.role.name or "").lower() == "admin"


def _create_context(form=None, errors=None):
    return {
        "isAdmin": _admin(),
        "services": Service.query.filter_by(status=True).all(),
        "specialists": Specialist.query.all(),
        "clients": [u for u in User.query.all() if not _admin(u)] if _admin() else [],
        "openingTime": OPENING_TIME,
        "closingTime": CLOSING_TIME,
        "today": date.today(),
        "form": form or {},
        "errors": errors or {},
    }


def _edit_context(appointment, form=None, errors=None):
    return {
        "appointment": appointment,
        "services": Service.query.filter_by(status=True).all(),
        "specialists": Specialist.query.all(),
        "openingTime": OPENING_TIME,
        "closingTime": CLOSING_TIME,
        "today": date.today(),
        "isAdmin": _admin(),
        "form": form or {},
        "errors": errors or {},
    }


def _form_values():
    return {
        "service_id": request.form.get("service_id") or "",
        "date": request.form.get("date") or "",
        "time": request.form.get("time") or "",
        "worker": request.form.get("worker") or "",
        "user_id": request.form.get("user_id") or "",
        "status": request.form.get("status") or "",
    }


def _validate(form, errors):
    service = None
    service_id = form["service_id"]
    if not service_id:
        errors["service_id"] = "Selecciona un servicio."
    elif not service_id.isdigit():
        errors["service_id"] = "El servicio seleccionado no es válido."
    else:
        service = db.session.get(Service, int(service_id))
        if service is None:
            errors["service_id"] = "El servicio seleccionado no existe."

    appointment_date = parse_date_field(form["date"], errors, "date", "La fecha")
    appointment_time = parse_time_field(form["time"], errors, "time", "La hora")
    form["worker"] = validate_optional(
        form["worker"], "La especialista", errors, "worker"
    )
    return service, appointment_date, appointment_time


def _slot_errors(form, errors, service, appointment_date, appointment_time, appointment_id=None):
    if service is None or appointment_date is None or appointment_time is None:
        return
    if "time" in errors or "date" in errors:
        return
    duration = service.duration if service.duration and service.duration > 0 else 30
    business_error = validate_business_hours(appointment_date, appointment_time, duration)
    if business_error:
        errors["time"] = business_error
        return
    end_time = (
        datetime.combine(appointment_date, appointment_time) + timedelta(minutes=duration)
    ).time()
    if has_conflict(
        appointment_date,
        appointment_time,
        end_time,
        form["worker"] or None,
        Appointment.query.all(),
        appointment_id,
    ):
        errors["time"] = "El horario seleccionado ya está ocupado. Elige otra hora."


@bp.route("")
@login_required
def index():
    if _admin():
        appointments = Appointment.query.order_by(Appointment.date.desc(), Appointment.time.desc()).all()
        return render_template("appointments/index.html", isAdmin=True, appointments=appointments)

    citas = (
        Appointment.query.filter_by(user_id=current_user.id)
        .order_by(Appointment.date.desc(), Appointment.time.desc())
        .all()
    )
    today = date.today()
    proximas = [c for c in citas if c.date is not None and c.date >= today and (c.status or "").lower() != "cancelada"]
    proximas.sort(key=lambda c: (c.date, c.time is None, c.time))
    historial = [
        c for c in citas
        if c.date is None or c.date < today or (c.status or "").lower() == "cancelada"
    ]
    historial.sort(key=lambda c: (c.date is None, c.date, c.time is None, c.time), reverse=True)

    return render_template(
        "appointments/index.html",
        isAdmin=False,
        appointments=citas,
        proximasCitas=proximas,
        historialCitas=historial,
    )


@bp.route("/create")
@login_required
def create():
    return render_template("appointments/create.html", **_create_context())


@bp.route("", methods=["POST"])
@login_required
def store():
    user = current_user
    if _admin() and request.form.get("user_id"):
        selected = db.session.get(User, int(request.form["user_id"]))
        if selected is None:
            abort(404)
        user = selected

    errors = {}
    form = _form_values()
    service, appointment_date, appointment_time = _validate(form, errors)
    _slot_errors(form, errors, service, appointment_date, appointment_time)

    if errors:
        return render_template("appointments/create.html", **_create_context(form, errors))

    appointment = Appointment(
        user=user,
        service=service,
        date=appointment_date,
        time=appointment_time,
        worker=form["worker"] or None,
        status="pendiente",
    )
    db.session.add(appointment)
    db.session.commit()

    flash("Cita creada correctamente.", "success")
    return redirect("/appointments")


@bp.route("/calendar")
@login_required
def calendar():
    appointments = Appointment.query.order_by(Appointment.date.asc(), Appointment.time.asc()).all()
    events = []
    for appointment in appointments:
        title = "Cita"
        if appointment.service is not None:
            title = appointment.service.name
            if appointment.user is not None:
                title += " - " + (appointment.user.name or "")
        events.append(
            {
                "title": title,
                "start": f"{appointment.date.isoformat()}T{appointment.time.strftime('%H:%M')}",
            }
        )
    return render_template("appointments/calendar.html", appointments=appointments, events=events)


@bp.route("/<int:appointment_id>/edit")
@login_required
def edit(appointment_id):
    appointment = db.session.get(Appointment, appointment_id)
    if appointment is None:
        abort(404)
    if not _admin() and appointment.user_id != current_user.id:
        return redirect("/appointments")

    form = {
        "service_id": appointment.service_id,
        "date": appointment.date.isoformat() if appointment.date else "",
        "time": appointment.time.strftime("%H:%M") if appointment.time else "",
        "worker": appointment.worker or "",
        "status": appointment.status or "",
    }
    return render_template(
        "appointments/edit.html", **_edit_context(appointment, form)
    )


@bp.route("/<int:appointment_id>", methods=["POST"])
@login_required
def update(appointment_id):
    appointment = db.session.get(Appointment, appointment_id)
    if appointment is None:
        abort(404)
    if not _admin() and appointment.user_id != current_user.id:
        return redirect("/appointments")

    errors = {}
    form = _form_values()
    service, appointment_date, appointment_time = _validate(form, errors)
    _slot_errors(
        form, errors, service, appointment_date, appointment_time, appointment.id
    )

    if errors:
        return render_template(
            "appointments/edit.html", **_edit_context(appointment, form, errors)
        )

    appointment.service = service
    appointment.date = appointment_date
    appointment.time = appointment_time
    appointment.worker = form["worker"] or None

    status = form["status"]
    if _admin() and status:
        if status not in VALID_STATUSES:
            errors["status"] = "El estado seleccionado no es válido."
            return render_template(
                "appointments/edit.html", **_edit_context(appointment, form, errors)
            )
        appointment.status = status

    db.session.commit()
    flash("Cita actualizada correctamente.", "success")
    return redirect("/appointments")


@bp.route("/<int:appointment_id>/status", methods=["POST"])
@login_required
def quick_status(appointment_id):
    if not _admin():
        return redirect("/appointments")

    appointment = db.session.get(Appointment, appointment_id)
    if appointment is None:
        abort(404)

    status = (request.form.get("status") or "").strip().lower()
    if status not in VALID_STATUSES:
        flash("Debes seleccionar un estado válido.", "error")
        return redirect("/appointments")

    appointment.status = status

    if status == "confirmada" and appointment.loyalty_stamped_at is None:
        card = LoyaltyCard.query.filter_by(user_id=appointment.user_id).first()
        if card is None:
            card = LoyaltyCard(user=appointment.user, stamps=0, available_rewards=0)
            db.session.add(card)
            db.session.flush()

        rewards_before = card.available_rewards
        card.add_stamp()
        appointment.loyalty_stamped_at = datetime.now()
        db.session.commit()

        if card.available_rewards > rewards_before:
            flash("Cita confirmada. La tarjeta se completó y la clienta tiene un servicio gratuito.", "success")
        else:
            flash("Cita confirmada correctamente.", "success")
    else:
        db.session.commit()
        flash("Estado actualizado correctamente.", "success")

    return redirect("/appointments")


@bp.route("/<int:appointment_id>/cancel", methods=["POST"])
@login_required
def cancel(appointment_id):
    appointment = db.session.get(Appointment, appointment_id)
    if appointment is None:
        abort(404)
    if not _admin() and appointment.user_id != current_user.id:
        return redirect("/appointments")

    if (appointment.status or "").lower() == "cancelada":
        flash("La cita ya estaba cancelada.", "error")
        return redirect("/appointments")

    appointment.status = "cancelada"
    db.session.commit()
    flash("Cita cancelada correctamente.", "success")
    return redirect("/appointments")
