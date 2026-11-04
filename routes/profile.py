"""Client profile and password management."""

from flask import Blueprint, flash, redirect, render_template, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import LoyaltyCard, User
from ..validators import (
    validate_email,
    validate_name,
    validate_password,
    validate_phone,
)

bp = Blueprint("profile", __name__)


def _context(user, form=None, errors=None, show_edit=False):
    context = {
        "user": user,
        "isAdmin": user.is_admin,
        "form": form or {},
        "errors": errors or {},
        "show_edit": show_edit,
    }
    if not user.is_admin:
        card = LoyaltyCard.query.filter_by(user_id=user.id).first()
        if card is None:
            card = LoyaltyCard(user=user, stamps=0, available_rewards=0)
            db.session.add(card)
            db.session.commit()
        context.update(
            card=card,
            progressPct=round(card.stamps * 100.0 / 9),
            remainingStamps=max(0, 9 - card.stamps),
        )
    return context


def _profile_form():
    return {
        "name": request.form.get("name"),
        "lastName": request.form.get("lastName"),
        "phone": request.form.get("phone"),
        "email": request.form.get("email"),
    }


@bp.route("/profile")
@login_required
def edit():
    return render_template("profile/edit.html", **_context(current_user))


@bp.route("/profile", methods=["POST"])
@login_required
def update():
    user = current_user
    errors = {}
    form = _profile_form()

    form["name"] = validate_name(form["name"], "El nombre", errors, "name")
    form["lastName"] = validate_name(
        form["lastName"], "El apellido", errors, "lastName", required=False
    )
    form["phone"] = validate_phone(form["phone"], errors, required=False)
    form["email"] = validate_email(form["email"], errors)

    if form["email"] and User.query.filter(
        User.email == form["email"], User.id != user.id
    ).first() is not None:
        errors["email"] = "Ya existe otro usuario con ese correo."

    if errors:
        return render_template(
            "profile/edit.html", **_context(user, form, errors, show_edit=True)
        )

    user.name = form["name"]
    user.last_name = form["lastName"] or None
    user.phone = form["phone"] or None
    user.email = form["email"]
    db.session.commit()

    flash("Perfil actualizado correctamente.", "success")
    return redirect("/profile")


@bp.route("/profile/password", methods=["POST"])
@login_required
def update_password():
    user = current_user
    errors = {}
    current_password = request.form.get("current_password") or ""
    password = request.form.get("password") or ""
    confirmation = request.form.get("password_confirmation") or ""

    if not user.check_password(current_password):
        errors["current_password"] = "La contraseña actual es incorrecta."
    validate_password(password, confirmation, errors)

    if errors:
        return render_template(
            "profile/edit.html",
            **_context(
                user,
                {"name": user.name, "lastName": user.last_name, "phone": user.phone, "email": user.email},
                errors,
                show_edit=True,
            ),
        )

    user.set_password(password)
    db.session.commit()
    flash("Contraseña actualizada correctamente.", "success")
    return redirect("/profile")
