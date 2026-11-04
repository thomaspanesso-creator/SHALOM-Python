"""Shopping bag (session based) and checkout."""

from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, session
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Inventory, InventoryMovement, Service

bp = Blueprint("cart", __name__, url_prefix="/carrito")


def _cart():
    return session.get("cart") or {}


def _save(cart):
    session["cart"] = cart
    session.modified = True


def _total(cart):
    total = Decimal("0")
    for item in cart.values():
        total += Decimal(str(item["price"])) * int(item["quantity"])
    return total


@bp.route("")
@login_required
def index():
    cart = _cart()
    return render_template("cart/index.html", cart=cart, total=_total(cart))


@bp.route("/anadir/<int:product_id>", methods=["POST"])
@login_required
def add(product_id):
    product = db.session.get(Inventory, product_id)
    if product is None:
        abort(404)

    if product.stock <= 0:
        flash(f"¡Lo sentimos! No hay stock de {product.product_name}", "error")
        return redirect("/carrito")

    cart = _cart()
    key = str(product_id)
    if key in cart:
        current_qty = int(cart[key]["quantity"])
        if current_qty + 1 > product.stock:
            flash(f"No puedes añadir más; solo quedan {product.stock} unidades.", "error")
            return redirect("/carrito")
        cart[key]["quantity"] = current_qty + 1
    else:
        cart[key] = {
            "name": product.product_name,
            "quantity": 1,
            "price": int(product.price),
            "image": product.image or "default-product.png",
            "type": "product",
        }

    _save(cart)
    flash(f"{product.product_name} se añadió al carrito.", "success")
    return redirect("/carrito")


@bp.route("/eliminar/<key>", methods=["POST"])
@login_required
def remove(key):
    cart = _cart()
    if key in cart:
        del cart[key]
        _save(cart)
    flash("Producto eliminado.", "success")
    return redirect("/carrito")


@bp.route("/anadir-servicio/<int:service_id>", methods=["POST"])
@login_required
def add_service(service_id):
    service = db.session.get(Service, service_id)
    if service is None:
        abort(404)

    cart = _cart()
    key = f"service_{service_id}"
    if key in cart:
        flash("Este servicio ya está en tu agenda de la bolsa.", "error")
        return redirect("/carrito")

    cart[key] = {
        "name": service.name + " (Servicio)",
        "quantity": 1,
        "price": int(service.price),
        "image": "service-icon",
        "type": "service",
    }
    _save(cart)
    flash(f"¡{service.name} se añadió a tu bolsa de experiencias!", "success")
    return redirect("/carrito")


@bp.route("/checkout", methods=["POST"])
@login_required
def checkout():
    cart = _cart()
    if not cart:
        flash("El carrito está vacío.", "error")
        return redirect("/carrito")

    user = current_user
    if user is None or not user.is_authenticated:
        flash("Debes iniciar sesión para completar la compra.", "error")
        return redirect("/carrito")

    # 1. Validate stock for every product before changing anything.
    for key, item in cart.items():
        if item.get("type") == "product":
            product = db.session.get(Inventory, int(key))
            if product is None or product.stock < int(item["quantity"]):
                flash(f"No hay suficiente stock de {item.get('name')}.", "error")
                return redirect("/carrito")

    # 2. Apply the sale and register the inventory movements.
    for key, item in cart.items():
        if item.get("type") == "product":
            product = db.session.get(Inventory, int(key))
            if product is None:
                continue
            quantity = int(item["quantity"])
            before = product.stock
            product.stock = before - quantity
            db.session.add(
                InventoryMovement(
                    product=product,
                    type="SALIDA",
                    quantity=-quantity,
                    stock_before=before,
                    stock_after=product.stock,
                    reason="Venta por carrito",
                    user=user,
                )
            )

    db.session.commit()
    session.pop("cart", None)
    flash("Compra realizada exitosamente. ¡Gracias!", "success")
    return redirect("/carrito")
