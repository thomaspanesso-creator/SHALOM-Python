"""Render every page that depends on an existing record (throwaway database)."""

import os
import sys
import tempfile
from datetime import date, time, timedelta

from shalom import create_app
from shalom.extensions import db
from shalom.models import Appointment, Inventory, Role, Service, Specialist, User


def next_working_day(offset=1):
    day = date.today() + timedelta(days=offset)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return day


def main():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///" + tmp.name, "PROPAGATE_EXCEPTIONS": True})

    with app.app_context():
        client_role = Role.query.filter_by(name="CLIENTE").first()
        client_user = User(name="Cliente", last_name="Test", email="render@example.com", role=client_role, enabled=True)
        client_user.set_password("render123")
        product = Inventory(product_name="Producto", category="Otros", stock=3, min_stock=1, price=1000)
        specialist = Specialist(name="Laura", specialty="Color")
        service = Service.query.first()
        db.session.add_all([client_user, product, specialist])
        db.session.flush()
        appointment = Appointment(
            user=client_user,
            service=service,
            date=next_working_day(),
            time=time(9, 0),
            status="pendiente",
            worker="Laura",
        )
        db.session.add(appointment)
        db.session.commit()
        ids = {
            "service": service.id,
            "specialist": specialist.id,
            "product": product.id,
            "user": client_user.id,
            "appointment": appointment.id,
        }

    routes = [
        f"/services/{ids['service']}/edit",
        f"/specialists/{ids['specialist']}/edit",
        f"/inventory/{ids['product']}/edit",
        f"/inventory/{ids['product']}/movimientos",
        f"/users/{ids['user']}/edit",
        f"/appointments/{ids['appointment']}/edit",
        "/inventory/movimientos",
        "/fidelizacion",
    ]

    failures = []
    with app.test_client() as client:
        client.post("/login", data={"username": "admin@shalom.com", "password": "admin123"}, follow_redirects=True)
        for route in routes:
            try:
                response = client.get(route)
                status = response.status_code
                print(("ok   " if status < 500 else "FAIL ") + route + f" -> {status}")
                if status >= 500:
                    failures.append(route)
            except Exception as exc:  # noqa: BLE001
                failures.append(route)
                print(f"ERROR {route}: {type(exc).__name__}: {exc}")

    print("FAILURES:", len(failures))
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
