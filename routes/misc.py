"""Legacy URL aliases kept from SalonController."""

from flask import Blueprint, redirect

bp = Blueprint("misc", __name__)

ALIASES = {
    "/citas": "/appointments",
    "/clientes": "/users",
    "/servicios": "/services",
    "/inventario": "/inventory",
    "/ventas": "/carrito",
    "/configuracion": "/profile",
}


def _make_redirect(target):
    def view():
        return redirect(target)

    return view


for _path, _target in ALIASES.items():
    bp.add_url_rule(_path, endpoint="alias_" + _path.strip("/").replace("-", "_"), view_func=_make_redirect(_target))
