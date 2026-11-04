"""Service catalog and admin CRUD."""

from flask import Blueprint, abort, flash, redirect, render_template, request
from flask_login import login_required

from ..decorators import admin_required
from ..extensions import db
from ..models import Appointment, Service
from ..validators import (
    parse_decimal,
    parse_int,
    validate_optional,
    validate_required,
)

bp = Blueprint("services", __name__, url_prefix="/services")


def _form_values():
    return {
        "name": request.form.get("name"),
        "description": request.form.get("description"),
        "price": request.form.get("price"),
        "duration": request.form.get("duration"),
        "category": request.form.get("category"),
        "image": request.form.get("image"),
        "status": request.form.get("status") in ("on", "true", "1", "si"),
    }


def _validate(form, errors):
    form["name"] = validate_required(form["name"], "El nombre del servicio", errors, "name")
    form["description"] = validate_required(
        form["description"], "La descripción", errors, "description", max_length=1000
    )
    form["price"] = parse_decimal(form["price"], errors, "price", "El precio")
    form["duration"] = parse_int(
        form["duration"], errors, "duration", "La duración", minimum=1, maximum=480
    )
    form["category"] = validate_optional(
        form["category"], "La categoría", errors, "category"
    )
    form["image"] = validate_optional(form["image"], "La imagen", errors, "image")
    return errors


@bp.route("")
@login_required
def index():
    from flask_login import current_user

    services = Service.query.filter_by(status=True).order_by(Service.name.asc()).all()
    return render_template("services/index.html", services=services, isAdmin=current_user.is_admin)


@bp.route("/admin")
@admin_required
def admin():
    # The original controller pointed at a template that does not exist; the
    # catalog page already contains the administration view.
    return redirect("/services")


@bp.route("/create")
@admin_required
def create():
    return render_template("services/create.html", service=None, form={}, errors={})


@bp.route("", methods=["POST"])
@admin_required
def store():
    errors = {}
    form = _form_values()
    _validate(form, errors)
    if errors:
        return render_template(
            "services/create.html", service=None, form=form, errors=errors
        )

    service = Service(
        name=form["name"],
        description=form["description"] or None,
        price=form["price"],
        duration=form["duration"],
        category=form["category"] or None,
        status=True,
        image=form["image"] or None,
    )
    db.session.add(service)
    db.session.commit()
    flash("Servicio creado correctamente.", "success")
    return redirect("/services")


@bp.route("/<int:service_id>/edit")
@admin_required
def edit(service_id):
    service = db.session.get(Service, service_id)
    if service is None:
        abort(404)
    form = {
        "name": service.name,
        "description": service.description,
        "price": service.price,
        "duration": service.duration,
        "category": service.category,
        "image": service.image,
        "status": service.status,
    }
    return render_template(
        "services/edit.html", service=service, form=form, errors={}
    )


@bp.route("/<int:service_id>", methods=["POST"])
@admin_required
def update(service_id):
    service = db.session.get(Service, service_id)
    if service is None:
        abort(404)

    errors = {}
    form = _form_values()
    _validate(form, errors)
    if errors:
        return render_template(
            "services/edit.html", service=service, form=form, errors=errors
        )

    service.name = form["name"]
    service.description = form["description"] or None
    service.price = form["price"]
    service.duration = form["duration"]
    service.category = form["category"] or None
    service.status = form["status"]
    service.image = form["image"] or None
    db.session.commit()

    flash("Servicio actualizado correctamente.", "success")
    return redirect("/services")


@bp.route("/<int:service_id>/delete", methods=["POST"])
@admin_required
def delete(service_id):
    service = db.session.get(Service, service_id)
    if service is None:
        abort(404)
    if Appointment.query.filter_by(service_id=service_id).first() is not None:
        flash("No se puede eliminar: el servicio tiene citas registradas.", "error")
        return redirect("/services")
    db.session.delete(service)
    db.session.commit()
    flash("Servicio eliminado correctamente.", "success")
    return redirect("/services")
