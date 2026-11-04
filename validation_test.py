"""Validation checks: invalid input is rejected with inline feedback."""

import tempfile

from shalom import create_app
from shalom.extensions import db
from shalom.models import Appointment, Inventory, Role, Service, Specialist, User

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


def main():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + tmp.name,
            "TESTING": True,
        }
    )

    with app.app_context():
        role = Role.query.filter_by(name="ADMIN").first()
        if role is None:
            role = Role(name="ADMIN")
            db.session.add(role)
            db.session.flush()
        if User.query.filter_by(email="admin@shalom.com").first() is None:
            admin = User(name="Admin", email="admin@shalom.com", role=role, enabled=True)
            admin.set_password("admin123")
            db.session.add(admin)

        service = Service(name="Manicure", price=25000, duration=45, status=True)
        specialist = Specialist(name="Laura", specialty="Uñas")
        product = Inventory(
            product_name="Esmalte", category="Uñas", min_stock=3, price=12000, stock=10
        )
        db.session.add_all([service, specialist, product])
        db.session.commit()
        service_id = service.id
        product_id = product.id

    with app.test_client() as client:
        # Registration -----------------------------------------------------
        response = client.post(
            "/register",
            data={
                "name": "A1",
                "email": "correo-invalido",
                "password": "corta",
                "password_confirmation": "otra",
            },
        )
        html = response.get_data(as_text=True)
        ok("register rejects invalid name", "solo puede contener letras" in html)
        ok("register rejects invalid email", "correo electrónico válido" in html)
        ok("register rejects weak password", "al menos 8" in html)
        ok("register shows inline feedback", "invalid-feedback" in html)

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
        )
        ok("register accepts valid data", response.status_code == 302, response.status_code)

        login(client, "admin@shalom.com", "admin123")

        # Profile ----------------------------------------------------------
        response = client.post(
            "/profile",
            data={"name": "", "email": "malo", "phone": "abc"},
        )
        html = response.get_data(as_text=True)
        ok("profile rejects empty name", "El nombre es obligatorio" in html)
        ok("profile rejects bad email", "correo electrónico válido" in html)
        ok("profile reopens edit form", 'id="datos-edit" class="d-none"' not in html)

        response = client.post(
            "/profile/password",
            data={
                "current_password": "incorrecta",
                "password": "secret123",
                "password_confirmation": "secret123",
            },
        )
        html = response.get_data(as_text=True)
        ok("password rejects wrong current", "contraseña actual es incorrecta" in html)
        ok("password shows inline error", "invalid-feedback" in html)

        # Appointment edit -------------------------------------------------
        response = client.post(
            f"/appointments/999",
            data={"service_id": "", "date": "", "time": "", "worker": ""},
        )
        ok("appointment edit 404 for unknown id", response.status_code == 404)

        with app.app_context():
            from datetime import date, time

            admin_user = User.query.filter_by(email="admin@shalom.com").first()
            appointment = Appointment(
                user_id=admin_user.id,
                service_id=service_id,
                date=date.today(),
                time=time(10, 0),
                status="pendiente",
            )
            db.session.add(appointment)
            db.session.commit()
            appointment_id = appointment.id

        response = client.post(
            f"/appointments/{appointment_id}",
            data={"service_id": "", "date": "2000-01-01", "time": "", "worker": ""},
        )
        html = response.get_data(as_text=True)
        ok("appointment edit rejects missing service", "Selecciona un servicio" in html)
        ok("appointment edit rejects past date", "anterior a hoy" in html)
        ok("appointment edit shows inline feedback", "invalid-feedback" in html)

        # Inventory --------------------------------------------------------
        response = client.post(
            "/inventory",
            data={"productName": "", "category": "", "minStock": "-2", "price": "abc"},
        )
        html = response.get_data(as_text=True)
        ok("inventory rejects empty product", "El nombre del producto es obligatorio" in html)
        ok("inventory rejects bad price", "El precio debe ser" in html)
        ok("inventory rejects negative stock", "no puede ser menor que 0" in html)

        # Services ---------------------------------------------------------
        response = client.post(
            "/services",
            data={
                "name": "",
                "description": "",
                "price": "-5",
                "duration": "0",
            },
        )
        html = response.get_data(as_text=True)
        ok("service rejects empty name", "El nombre del servicio es obligatorio" in html)
        ok("service rejects negative price", "no puede ser menor que 0" in html)
        ok("service rejects duration 0", "La duración" in html)

        # Movements --------------------------------------------------------
        response = client.post(
            f"/inventory/{product_id}/movimientos",
            data={"type": "SALIDA", "quantity": "999", "reason": ""},
        )
        html = response.get_data(as_text=True)
        ok("movement rejects insufficient stock", "Stock insuficiente" in html)
        ok("movement shows inline error", "invalid-feedback" in html)

    print("FAILURES:", len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
