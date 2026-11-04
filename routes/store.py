"""Public storefront (requires an authenticated session, like the original app)."""

from flask import Blueprint, render_template
from flask_login import login_required

from ..models import Inventory, Service

bp = Blueprint("store", __name__)


@bp.route("/tienda")
@login_required
def index():
    return render_template(
        "store/index.html",
        productos=Inventory.query.all(),
        servicios=Service.query.all(),
    )
