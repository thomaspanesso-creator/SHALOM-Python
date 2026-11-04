"""Specialist catalog and admin CRUD."""

from flask import Blueprint, abort, flash, redirect, render_template, request
from flask_login import current_user, login_required

from ..decorators import admin_required
from ..extensions import db
from ..models import Specialist
from ..validators import validate_name, validate_optional

bp = Blueprint("specialists", __name__, url_prefix="/specialists")


def _form_values():
    return {
        "name": request.form.get("name"),
        "specialty": request.form.get("specialty"),
        "description": request.form.get("description"),
        "image": request.form.get("image"),
    }


def _validate(form, errors):
    form["name"] = validate_name(form["name"], "El nombre", errors, "name")
    form["specialty"] = validate_name(
        form["specialty"], "La especialidad", errors, "specialty"
    )
    form["description"] = validate_optional(
        form["description"], "La descripción", errors, "description", max_length=1000
    )
    form["image"] = validate_optional(form["image"], "La imagen", errors, "image")
    return errors


@bp.route("")
@login_required
def index():
    return render_template(
        "specialists/index.html",
        specialists=Specialist.query.all(),
        isAdmin=current_user.is_admin,
    )


@bp.route("/create")
@admin_required
def create():
    return render_template(
        "specialists/create.html", specialist=None, form={}, errors={}
    )


@bp.route("", methods=["POST"])
@admin_required
def store():
    errors = {}
    form = _form_values()
    _validate(form, errors)
    if errors:
        return render_template(
            "specialists/create.html", specialist=None, form=form, errors=errors
        )

    specialist = Specialist(
        name=form["name"],
        specialty=form["specialty"],
        description=form["description"] or None,
        image=form["image"] or None,
    )
    db.session.add(specialist)
    db.session.commit()
    flash("Especialista creada correctamente", "success")
    return redirect("/specialists")


@bp.route("/<int:specialist_id>/edit")
@admin_required
def edit(specialist_id):
    specialist = db.session.get(Specialist, specialist_id)
    if specialist is None:
        abort(404)
    form = {
        "name": specialist.name,
        "specialty": specialist.specialty,
        "description": specialist.description,
        "image": specialist.image,
    }
    return render_template(
        "specialists/edit.html", specialist=specialist, form=form, errors={}
    )


@bp.route("/<int:specialist_id>", methods=["POST"])
@admin_required
def update(specialist_id):
    specialist = db.session.get(Specialist, specialist_id)
    if specialist is None:
        abort(404)

    errors = {}
    form = _form_values()
    _validate(form, errors)
    if errors:
        return render_template(
            "specialists/edit.html", specialist=specialist, form=form, errors=errors
        )

    specialist.name = form["name"]
    specialist.specialty = form["specialty"]
    specialist.description = form["description"] or None
    db.session.commit()
    flash("Especialista actualizada correctamente", "success")
    return redirect("/specialists")


@bp.route("/<int:specialist_id>/delete", methods=["POST"])
@admin_required
def destroy(specialist_id):
    specialist = db.session.get(Specialist, specialist_id)
    if specialist is None:
        abort(404)
    db.session.delete(specialist)
    db.session.commit()
    flash("Especialista eliminada correctamente", "success")
    return redirect("/specialists")
