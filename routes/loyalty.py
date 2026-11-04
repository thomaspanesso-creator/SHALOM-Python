"""Loyalty cards: client card view and admin stamp management."""

from flask import Blueprint, abort, flash, redirect, render_template
from flask_login import current_user, login_required

from ..decorators import admin_required
from ..extensions import db
from ..models import LoyaltyCard, User

bp = Blueprint("loyalty", __name__)


def _get_or_create(user):
    card = LoyaltyCard.query.filter_by(user_id=user.id).first()
    if card is None:
        card = LoyaltyCard(user=user, stamps=0, available_rewards=0)
        db.session.add(card)
        db.session.commit()
    return card


@bp.route("/mi-tarjeta")
@login_required
def show():
    card = _get_or_create(current_user)
    return render_template(
        "loyalty/show.html",
        card=card,
        user=current_user,
        remainingStamps=max(0, 9 - card.stamps),
        progressPct=round(card.stamps * 100.0 / 9),
    )


@bp.route("/fidelizacion")
@admin_required
def index():
    return render_template("loyalty/index.html", cards=LoyaltyCard.query.all())


@bp.route("/fidelizacion/<int:user_id>/sello", methods=["POST"])
@admin_required
def add_stamp(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)

    card = _get_or_create(user)
    rewards_before = card.available_rewards
    card.add_stamp()
    db.session.commit()

    if card.available_rewards > rewards_before:
        flash("Tarjeta completada. La clienta tiene un servicio gratuito disponible.", "success")
    else:
        flash("Sello agregado correctamente a la tarjeta de fidelidad.", "success")
    return redirect("/fidelizacion")
