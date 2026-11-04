"""User administration (ADMIN only)."""

from flask import Blueprint, abort, flash, redirect, render_template, request
from flask_login import current_user

from ..decorators import admin_required
from ..extensions import db
from ..models import Appointment, Role, User
from ..validators import (
    validate_email,
    validate_name,
    validate_optional,
    validate_password,
    validate_phone,
)

bp = Blueprint("users", __name__, url_prefix="/users")


def _roles():
    return Role.query.order_by(Role.id).all()


def _form_values(request_form):
    return {
        "name": request_form.get("name"),
        "lastName": request_form.get("lastName"),
        "phone": request_form.get("phone"),
        "email": request_form.get("email"),
        "role_id": request_form.get("role.id") or request_form.get("role_id") or "",
    }


def _validate(form, errors, *, creating):
    form["name"] = validate_name(form["name"], "El nombre", errors, "name")
    form["lastName"] = validate_name(
        form["lastName"], "El apellido", errors, "lastName", required=False
    )
    form["phone"] = validate_phone(form["phone"], errors, required=False)
    form["email"] = validate_email(form["email"], errors)

    role_id = (form.get("role_id") or "").strip()
    if not role_id:
        errors["role_id"] = "Debes seleccionar un rol."
    elif not role_id.isdigit() or db.session.get(Role, int(role_id)) is None:
        errors["role_id"] = "El rol seleccionado no es válido."

    password = request.form.get("password") or ""
    confirmation = request.form.get("password_confirmation") or ""
    validate_password(password, confirmation, errors, required=creating)
    return password


@bp.route("")
@admin_required
def index():
    return render_template("users/index.html", users=User.query.order_by(User.id.asc()).all())


@bp.route("/create")
@admin_required
def create():
    return render_template(
        "users/create.html", user=None, roles=_roles(), form={}, errors={}
    )


@bp.route("", methods=["POST"])
@admin_required
def store():
    errors = {}
    form = _form_values(request.form)
    password = _validate(form, errors, creating=True)

    if form["email"] and User.query.filter_by(email=form["email"]).first() is not None:
        errors["email"] = "Ya existe un usuario con ese correo."

    if errors:
        return render_template(
            "users/create.html", user=None, roles=_roles(), form=form, errors=errors
        )

    role = db.session.get(Role, int(form["role_id"]))
    user = User(
        name=form["name"],
        last_name=form["lastName"] or None,
        phone=form["phone"] or None,
        email=form["email"],
        role=role,
        enabled=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    flash("Usuario creado correctamente.", "success")
    return redirect("/users")


@bp.route("/<int:user_id>/edit")
@admin_required
def edit(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    form = {
        "name": user.name,
        "lastName": user.last_name,
        "phone": user.phone,
        "email": user.email,
        "role_id": user.role_id,
    }
    return render_template(
        "users/edit.html", user=user, roles=_roles(), form=form, errors={}
    )


@bp.route("/<int:user_id>", methods=["POST"])
@admin_required
def update(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)

    errors = {}
    form = _form_values(request.form)
    password = _validate(form, errors, creating=False)

    if form["email"] and User.query.filter(
        User.email == form["email"], User.id != user_id
    ).first() is not None:
        errors["email"] = "Ya existe otro usuario con ese correo."

    if errors:
        return render_template(
            "users/edit.html", user=user, roles=_roles(), form=form, errors=errors
        )

    role = db.session.get(Role, int(form["role_id"]))
    user.name = form["name"]
    user.last_name = form["lastName"] or None
    user.phone = form["phone"] or None
    user.email = form["email"]
    user.role = role
    if password:
        user.set_password(password)
    db.session.commit()

    flash("Usuario actualizado correctamente.", "success")
    return redirect("/users")


@bp.route("/<int:user_id>/delete", methods=["POST"])
@admin_required
def destroy(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("El usuario no existe.", "error")
        return redirect("/users")
    if user.id == current_user.id:
        flash("No se puede eliminar la sesión que estás usando.", "error")
        return redirect("/users")
    if Appointment.query.filter_by(user_id=user_id).first() is not None:
        flash("No se puede eliminar: el usuario tiene citas registradas.", "error")
        return redirect("/users")

    db.session.delete(user)
    db.session.commit()
    flash("Usuario eliminado correctamente.", "success")
    return redirect("/users")
