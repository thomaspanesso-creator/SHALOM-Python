"""End-to-end flow checks against a throwaway SQLite database."""

import os
import sys
import tempfile
from datetime import date, datetime, time, timedelta

from shalom import create_app
from shalom.extensions import db
from shalom.models import Appointment, Inventory, InventoryMovement, Role, Service, Specialist, User

FAILS = []


def ok(label, condition, detail=""):
    if condition:
        print(f"ok   {label}")
    else:
        FAILS.append(label)
        print(f"FAIL {label} {detail}")


def login(client, email, password):
    return client.post(
        "/login",
        data={"username": email, "password": password},
        follow_redirects=True,
    )


def next_working_day(offset=1):
    day = date.today() + timedelta(days=offset)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return day


def main():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + tmp.name,
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
        }
    )

    with app.test_client() as client:
        # -- registration --------------------------------------------------
        response = client.post(
            "/register",
            data={
                "name": "Ana",
                "lastName": "Perez",
                "phone": "3001234567",
                "email": "ana@example.com",
                "password": "secret123",
                "password_confirmation": "secret123",
            },
            follow_redirects=True,
        )
        with app.app_context():
            ana = User.query.filter_by(email="ana@example.com").first()
            ana_role = ana.role.name if ana and ana.role else None
            ana_id = ana.id if ana else None
        ok("register creates client", ana_role == "CLIENTE")

        login(client, "ana@example.com", "secret123")
        response = client.get("/dashboard")
        ok("client dashboard", response.status_code == 200)

        # -- appointment create -------------------------------------------
        with app.app_context():
            service = Service.query.first()
            service_id = service.id
            service_duration = service.duration

        day = next_working_day()
        response = client.post(
            "/appointments",
            data={"service_id": service_id, "date": day.isoformat(), "time": "10:00", "worker": "Laura"},
            follow_redirects=True,
        )
        with app.app_context():
            appointment = Appointment.query.filter_by(user_id=ana_id).first()
            appointment_date = appointment.date if appointment else None
        ok("appointment created", appointment_date == day)

        response = client.post(
            "/appointments",
            data={"service_id": service_id, "date": day.isoformat(), "time": "10:00", "worker": "Laura"},
            follow_redirects=True,
        )
        with app.app_context():
            count = Appointment.query.filter_by(user_id=ana_id).count()
        ok("duplicate slot rejected", count == 1, f"count={count}")

        sunday = date.today() + timedelta(days=(6 - date.today().weekday()) % 7 or 7)
        while sunday.weekday() != 6:
            sunday += timedelta(days=1)
        client.post(
            "/appointments",
            data={"service_id": service_id, "date": sunday.isoformat(), "time": "10:00"},
            follow_redirects=True,
        )
        with app.app_context():
            count = Appointment.query.filter_by(user_id=ana_id).count()
        ok("sunday rejected", count == 1, f"count={count}")

        # -- edit and cancel ----------------------------------------------
        with app.app_context():
            appointment_id = Appointment.query.filter_by(user_id=ana_id).first().id
        response = client.post(
            f"/appointments/{appointment_id}",
            data={
                "service_id": service_id,
                "date": next_working_day(2).isoformat(),
                "time": "11:00",
                "worker": "Laura",
            },
            follow_redirects=True,
        )
        with app.app_context():
            edited = db.session.get(Appointment, appointment_id)
            edited_time = edited.time
        ok("appointment edited", edited_time == time(11, 0), str(edited_time))

        response = client.post(f"/appointments/{appointment_id}/cancel", follow_redirects=True)
        with app.app_context():
            edited = db.session.get(Appointment, appointment_id)
            edited_status = edited.status
        ok("appointment cancelled", edited_status == "cancelada")

        # -- cart ----------------------------------------------------------
        response = client.post(f"/carrito/anadir-servicio/{service_id}", follow_redirects=True)
        ok("cart add service", response.status_code == 200)
        response = client.post("/carrito/checkout", follow_redirects=True)
        ok("cart checkout", response.status_code == 200)

        # -- profile -------------------------------------------------------
        response = client.post(
            "/profile",
            data={"name": "Ana Maria", "lastName": "Perez", "phone": "3009999999", "email": "ana@example.com"},
            follow_redirects=True,
        )
        with app.app_context():
            ana = User.query.filter_by(email="ana@example.com").first()
            ana_name = ana.name
        ok("profile updated", ana_name == "Ana Maria")
        response = client.post(
            "/profile/password",
            data={"current_password": "secret123", "password": "secret456", "password_confirmation": "secret456"},
            follow_redirects=True,
        )
        with app.app_context():
            ana = User.query.filter_by(email="ana@example.com").first()
            password_ok = ana.check_password("secret456")
        ok("password updated", password_ok)

    # -- admin flows -------------------------------------------------------
    with app.test_client() as admin:
        login(admin, "admin@shalom.com", "admin123")

        response = admin.post(
            "/specialists",
            data={"name": "Laura Gomez", "specialty": "Colorista", "description": "Color", "image": ""},
            follow_redirects=True,
        )
        with app.app_context():
            specialist = Specialist.query.filter_by(name="Laura Gomez").first()
            specialist_id = specialist.id if specialist else None
        ok("specialist created", specialist_id is not None)
        response = admin.post(
            f"/specialists/{specialist_id}",
            data={"name": "Laura Gomez", "specialty": "Color y corte"},
            follow_redirects=True,
        )
        with app.app_context():
            specialist = db.session.get(Specialist, specialist_id)
            specialist_specialty = specialist.specialty
        ok("specialist updated", specialist_specialty == "Color y corte")

        response = admin.post(
            "/services",
            data={"name": "Servicio test", "description": "Desc", "price": "15000", "duration": "30"},
            follow_redirects=True,
        )
        with app.app_context():
            test_service = Service.query.filter_by(name="Servicio test").first()
            service_pk = test_service.id if test_service else None
        ok("service created", service_pk is not None)
        response = admin.post(
            f"/services/{service_pk}",
            data={"name": "Servicio test 2", "description": "Desc", "price": "20000", "duration": "45", "status": "on"},
            follow_redirects=True,
        )
        with app.app_context():
            test_service = Service.query.filter_by(name="Servicio test 2").first()
            service_status = test_service.status if test_service else None
        ok("service updated", service_status is True)

        response = admin.post(
            "/inventory",
            data={"productName": "Producto test", "brand": "Marca", "minStock": "2", "category": "Otros", "description": "d", "price": "5000"},
            follow_redirects=True,
        )
        with app.app_context():
            product = Inventory.query.filter_by(product_name="Producto test").first()
            product_id = product.id if product else None
            product_stock = product.stock if product else None
        ok("inventory created", product_id is not None and product_stock == 0)
        response = admin.post(
            f"/inventory/{product_id}/movimientos",
            data={"type": "ENTRADA", "quantity": "10", "reason": "Compra"},
            follow_redirects=True,
        )
        with app.app_context():
            product = Inventory.query.filter_by(product_name="Producto test").first()
            movement = InventoryMovement.query.filter_by(product_id=product.id).first()
            flow_ok = product.stock == 10 and movement is not None and movement.stock_after == 10
        ok("stock movement", flow_ok)
        response = admin.post(f"/inventory/{product_id}/delete", follow_redirects=True)
        with app.app_context():
            still_there = Inventory.query.filter_by(product_name="Producto test").first() is not None
        ok("product with movements not deleted", still_there)

        response = admin.post(
            "/users",
            data={
                "name": "Carlos",
                "lastName": "Ruiz",
                "phone": "3001112233",
                "email": "carlos@example.com",
                "password": "carlos123",
                "password_confirmation": "carlos123",
                "role.id": "2",
            },
            follow_redirects=True,
        )
        with app.app_context():
            carlos = User.query.filter_by(email="carlos@example.com").first()
            carlos_role = carlos.role.name if carlos and carlos.role else None
            carlos_id = carlos.id if carlos else None
        ok("user created", carlos_role == "CLIENTE")
        response = admin.post(
            f"/users/{carlos_id}",
            data={
                "name": "Carlos A",
                "lastName": "Ruiz",
                "phone": "3001112233",
                "email": "carlos@example.com",
                "password": "",
                "password_confirmation": "",
                "role.id": "2",
            },
            follow_redirects=True,
        )
        with app.app_context():
            carlos = db.session.get(User, carlos_id)
            carlos_name = carlos.name
        ok("user updated", carlos_name == "Carlos A")
        response = admin.post(f"/users/{carlos_id}/delete", follow_redirects=True)
        with app.app_context():
            carlos = User.query.filter_by(email="carlos@example.com").first()
        ok("user deleted", carlos is None)

        # confirm an appointment -> stamp
        with app.app_context():
            service_pk = Service.query.first().id
            ana_id = User.query.filter_by(email="ana@example.com").first().id
        admin.post(
            "/appointments",
            data={
                "user_id": ana_id,
                "service_id": service_pk,
                "date": next_working_day(3).isoformat(),
                "time": "12:00",
                "worker": "Laura",
            },
            follow_redirects=True,
        )
        with app.app_context():
            pending = Appointment.query.filter_by(status="pendiente").order_by(Appointment.id.desc()).first()
            pending_id = pending.id if pending else None
            pending_user = pending.user_id if pending else None
        ok("admin creates appointment for client", pending_id is not None)
        if pending_id:
            admin.post(f"/appointments/{pending_id}/status", data={"status": "confirmada"}, follow_redirects=True)
            with app.app_context():
                from shalom.models import LoyaltyCard

                card = LoyaltyCard.query.filter_by(user_id=pending_user).first()
                stamps = card.stamps if card else None
            ok("loyalty stamp on confirm", stamps == 1, str(stamps))

    app_errors = len(FAILS)
    print("FAILURES:", app_errors)
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    return 1 if app_errors else 0


if __name__ == "__main__":
    sys.exit(main())
