"""Inventory and stock movements."""

from flask import Blueprint, abort, flash, redirect, render_template, request
from flask_login import current_user

from ..decorators import admin_required
from ..extensions import db
from ..models import Inventory, InventoryMovement
from ..validators import (
    parse_decimal,
    parse_int,
    validate_optional,
    validate_required,
)

bp = Blueprint("inventory", __name__, url_prefix="/inventory")


def _form_values():
    return {
        "productName": request.form.get("productName"),
        "brand": request.form.get("brand"),
        "category": request.form.get("category"),
        "description": request.form.get("description"),
        "minStock": request.form.get("minStock"),
        "price": request.form.get("price"),
        "image": request.form.get("image"),
    }


def _validate(form, errors):
    form["productName"] = validate_required(
        form["productName"], "El nombre del producto", errors, "productName"
    )
    form["brand"] = validate_optional(form["brand"], "La marca", errors, "brand")
    form["category"] = validate_required(
        form["category"], "La categoría", errors, "category"
    )
    form["description"] = validate_optional(
        form["description"], "La descripción", errors, "description", max_length=1000
    )
    form["minStock"] = parse_int(
        form["minStock"] or "0", errors, "minStock", "El stock mínimo", minimum=0
    )
    form["price"] = parse_decimal(form["price"], errors, "price", "El precio")
    form["image"] = validate_optional(form["image"], "La imagen", errors, "image")
    return errors


def _movements_context(product=None):
    if product is not None:
        movements = (
            InventoryMovement.query.filter_by(product_id=product.id)
            .order_by(InventoryMovement.created_at.desc())
            .all()
        )
    else:
        movements = InventoryMovement.query.order_by(
            InventoryMovement.created_at.desc()
        ).all()
    return {
        "movements": movements,
        "product": product,
        "products": Inventory.query.order_by(Inventory.id.asc()).all(),
        "form": {},
        "errors": {},
    }


@bp.route("")
@admin_required
def index():
    items = Inventory.query.order_by(Inventory.id.asc()).all()
    return render_template(
        "inventory/index.html",
        items=items,
        totalProductos=len(items),
        stockBajo=sum(1 for item in items if item.stock <= item.min_stock),
        sinStock=sum(1 for item in items if item.stock == 0),
    )


@bp.route("/create")
@admin_required
def create():
    return render_template("inventory/create.html", item=None, form={}, errors={})


@bp.route("", methods=["POST"])
@admin_required
def store():
    errors = {}
    form = _form_values()
    _validate(form, errors)
    if errors:
        return render_template(
            "inventory/create.html", item=None, form=form, errors=errors
        )

    item = Inventory(
        product_name=form["productName"],
        brand=form["brand"] or None,
        category=form["category"] or None,
        description=form["description"] or None,
        min_stock=form["minStock"],
        price=form["price"],
        image=form["image"] or None,
        stock=0,
    )
    db.session.add(item)
    db.session.commit()
    flash("Producto agregado correctamente", "success")
    return redirect("/inventory")


@bp.route("/<int:item_id>/edit")
@admin_required
def edit(item_id):
    item = db.session.get(Inventory, item_id)
    if item is None:
        abort(404)
    form = {
        "productName": item.product_name,
        "brand": item.brand,
        "category": item.category,
        "description": item.description,
        "minStock": item.min_stock,
        "price": item.price,
        "image": item.image,
    }
    return render_template("inventory/edit.html", item=item, form=form, errors={})


@bp.route("/<int:item_id>", methods=["POST"])
@admin_required
def update(item_id):
    item = db.session.get(Inventory, item_id)
    if item is None:
        flash("El producto no existe.", "error")
        return redirect("/inventory")

    errors = {}
    form = _form_values()
    _validate(form, errors)
    if errors:
        return render_template("inventory/edit.html", item=item, form=form, errors=errors)

    item.product_name = form["productName"]
    item.brand = form["brand"] or None
    item.category = form["category"] or None
    item.description = form["description"] or None
    item.min_stock = form["minStock"]
    item.price = form["price"]
    if form["image"]:
        item.image = form["image"]
    db.session.commit()
    flash("Producto actualizado correctamente", "success")
    return redirect("/inventory")


@bp.route("/<int:item_id>/delete", methods=["POST"])
@admin_required
def destroy(item_id):
    item = db.session.get(Inventory, item_id)
    if item is None:
        abort(404)
    if InventoryMovement.query.filter_by(product_id=item_id).first() is not None:
        flash("No se puede eliminar: el producto tiene movimientos de inventario registrados.", "error")
        return redirect("/inventory")
    db.session.delete(item)
    db.session.commit()
    flash("Producto eliminado correctamente", "success")
    return redirect("/inventory")


@bp.route("/movimientos")
@admin_required
def all_movements():
    return render_template("inventory/movements.html", **_movements_context())


@bp.route("/<int:item_id>/movimientos")
@admin_required
def movements(item_id):
    product = db.session.get(Inventory, item_id)
    if product is None:
        abort(404)
    return render_template("inventory/movements.html", **_movements_context(product))


def _register_movement(product):
    errors = {}
    movement_type = (request.form.get("type") or "").upper()
    if movement_type not in ("ENTRADA", "SALIDA", "AJUSTE"):
        errors["type"] = "Selecciona un tipo de movimiento válido."

    quantity = parse_int(
        request.form.get("quantity"), errors, "quantity", "La cantidad", minimum=0
    )
    reason = validate_optional(
        request.form.get("reason"), "La razón", errors, "reason", max_length=255
    )

    if errors:
        context = _movements_context(product)
        context["form"] = {
            "type": movement_type,
            "quantity": request.form.get("quantity"),
            "reason": reason,
        }
        context["errors"] = errors
        return render_template("inventory/movements.html", **context)

    before = product.stock
    movement = InventoryMovement(
        product=product,
        type=movement_type,
        reason=reason or None,
        user=current_user,
    )

    if movement_type == "ENTRADA":
        movement.quantity = quantity
        product.stock = before + quantity
    elif movement_type == "SALIDA":
        if before < quantity:
            context = _movements_context(product)
            context["form"] = {
                "type": movement_type,
                "quantity": quantity,
                "reason": reason,
            }
            context["errors"] = {
                "quantity": f"Stock insuficiente. Disponible: {before}."
            }
            return render_template("inventory/movements.html", **context)
        movement.quantity = -quantity
        product.stock = before - quantity
    else:  # AJUSTE: quantity is the new stock
        movement.quantity = quantity - before
        product.stock = quantity

    movement.stock_before = before
    movement.stock_after = product.stock
    db.session.add(movement)
    db.session.commit()

    flash("Movimiento registrado correctamente.", "success")
    return redirect(f"/inventory/{product.id}/movimientos")


@bp.route("/<int:item_id>/movimientos", methods=["POST"])
@admin_required
def add_movement(item_id):
    product = db.session.get(Inventory, item_id)
    if product is None:
        abort(404)
    return _register_movement(product)


@bp.route("/movimientos", methods=["POST"])
@admin_required
def add_movement_global():
    product_id = request.form.get("productId")
    errors = {}
    if not product_id or not product_id.isdigit():
        errors["productId"] = "Selecciona un producto."
        product = None
    else:
        product = db.session.get(Inventory, int(product_id))
        if product is None:
            errors["productId"] = "El producto seleccionado no existe."

    if errors:
        context = _movements_context()
        context["form"] = {
            "productId": product_id,
            "type": request.form.get("type"),
            "quantity": request.form.get("quantity"),
            "reason": request.form.get("reason"),
        }
        context["errors"] = errors
        return render_template("inventory/movements.html", **context)

    return _register_movement(product)
