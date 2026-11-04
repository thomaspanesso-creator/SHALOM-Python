"""Smoke test: login as admin/client and request every page."""

import sys
import traceback

from shalom import create_app


GET_ROUTES = [
    "/",
    "/dashboard",
    "/appointments",
    "/appointments/create",
    "/appointments/calendar",
    "/services",
    "/specialists",
    "/tienda",
    "/carrito",
    "/mi-tarjeta",
    "/profile",
]

ADMIN_ROUTES = [
    "/fidelizacion",
    "/inventory",
    "/inventory/create",
    "/inventory/movimientos",
    "/users",
    "/users/create",
    "/services/create",
    "/specialists/create",
    "/reportes/citas",
    "/reportes/especialistas",
    "/reportes/ingresos",
    "/reportes/inventario-bajo",
    "/reportes/servicios",
    "/api/reportes/ventas",
    "/citas",
    "/clientes",
    "/servicios",
    "/inventario",
    "/ventas",
    "/configuracion",
]


def check(client, routes, label):
    failures = 0
    for route in routes:
        try:
            response = client.get(route, follow_redirects=False)
            status = response.status_code
            if status >= 500:
                failures += 1
                body = response.get_data(as_text=True)
                print(f"FAIL [{label}] {route} -> {status}")
                print(body[-1500:])
            elif status in (301, 302, 303):
                print(f"redirect [{label}] {route} -> {status} {response.headers.get('Location')}")
            elif status == 403:
                print(f"forbidden [{label}] {route} -> 403")
            else:
                print(f"ok  [{label}] {route} -> {status}")
        except Exception:
            failures += 1
            print(f"ERROR [{label}] {route}")
            traceback.print_exc()
    return failures


def main():
    app = create_app()
    app.config["PROPAGATE_EXCEPTIONS"] = True
    app.config["TESTING"] = True

    from shalom.extensions import db
    from shalom.models import Role, User

    with app.app_context():
        if User.query.filter_by(email="cliente@example.com").first() is None:
            role = Role.query.filter_by(name="CLIENTE").first()
            client_user = User(name="Cliente", last_name="Prueba", email="cliente@example.com", role=role, enabled=True)
            client_user.set_password("cliente123")
            db.session.add(client_user)
            db.session.commit()

    failures = 0
    with app.test_client() as client:
        response = client.post(
            "/login",
            data={"username": "admin@shalom.com", "password": "admin123"},
            follow_redirects=True,
        )
        print("login admin ->", response.status_code, response.request.path)
        failures += check(client, GET_ROUTES + ADMIN_ROUTES, "admin")

    with app.test_client() as client:
        response = client.post(
            "/login",
            data={"username": "cliente@example.com", "password": "cliente123"},
            follow_redirects=True,
        )
        print("login client ->", response.status_code, response.request.path)
        failures += check(client, GET_ROUTES, "client")

    print("FAILURES:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
