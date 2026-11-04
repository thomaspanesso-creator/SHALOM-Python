"""Authentication, registration and password recovery."""

import json
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import PasswordResetToken, Role, User
from ..validators import (
    validate_email,
    validate_name,
    validate_password,
    validate_phone,
)


bp = Blueprint("auth", __name__)

RESET_TOKEN_HOURS = 1


def _logged_in():
    return current_user.is_authenticated


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if _logged_in():
        return redirect("/dashboard")

    if request.method == "POST":
        email = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        remember = request.form.get("remember-me") == "true"

        user = User.query.filter_by(email=email).first()
        if user is not None and user.enabled and user.check_password(password):
            login_user(user, remember=remember)
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect("/dashboard")

        return redirect("/login?error=true")

    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    session.pop("cart", None)
    return redirect("/")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
@bp.route("/register", methods=["GET", "POST"])
def register():
    if _logged_in():
        return redirect("/dashboard")

    form = {}
    errors = {}

    if request.method == "POST":
        form = {
            "name": request.form.get("name"),
            "lastName": request.form.get("lastName"),
            "phone": request.form.get("phone"),
            "email": request.form.get("email"),
        }
        password = request.form.get("password") or ""
        confirmation = request.form.get("password_confirmation") or ""

        form["name"] = validate_name(form["name"], "El nombre", errors, "name")
        form["lastName"] = validate_name(
            form["lastName"], "El apellido", errors, "lastName", required=False
        )
        form["phone"] = validate_phone(form["phone"], errors, required=False)
        form["email"] = validate_email(form["email"], errors)
        validate_password(password, confirmation, errors)

        if form["email"] and User.query.filter_by(email=form["email"]).first() is not None:
            errors["email"] = "Este correo electrónico ya está registrado."

        if not errors:
            role = Role.query.filter_by(name="CLIENTE").first()
            if role is None:
                role = Role(name="CLIENTE")
                db.session.add(role)
                db.session.flush()

            user = User(
                name=form["name"],
                last_name=form["lastName"] or None,
                phone=form["phone"] or None,
                email=form["email"],
                role=role,
                enabled=True,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            flash("¡Bienvenida a SHALOM! Tu cuenta fue creada correctamente.", "success")
            return redirect("/login")

    return render_template("auth/register.html", form=form, errors=errors)


@bp.route("/")
def home():
    if _logged_in():
        return redirect("/dashboard")
    return render_template("welcome.html")


# ---------------------------------------------------------------------------
# Password recovery
# ---------------------------------------------------------------------------
@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        errors = {}
        email = validate_email(request.form.get("email"), errors)
        if errors:
            return render_template(
                "auth/forgot.html", error=errors["email"], frEmail=email
            )

        user = User.query.filter_by(email=email).first()
        if user is None:
            return render_template("auth/forgot.html", emailNotFound=True, frEmail=email)

        PasswordResetToken.query.filter_by(email=email).delete()
        token = PasswordResetToken(
            token=secrets.token_hex(32),
            email=email,
            expires_at=datetime.now() + timedelta(hours=RESET_TOKEN_HOURS),
        )
        db.session.add(token)
        db.session.commit()

        return render_template(
            "auth/forgot.html",
            resetSent=True,
            resetLink=url_for("auth.reset_password", token=token.token),
            frEmail=email,
        )

    return render_template("auth/forgot.html")


def _valid_token(token):
    record = PasswordResetToken.query.filter_by(token=token).first()
    return record is not None and record.expires_at is not None and record.expires_at > datetime.now()


@bp.route("/password/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    if request.method == "POST":
        if not _valid_token(token):
            flash("El enlace no es válido o ya expiró.", "error")
            return redirect("/forgot-password")

        errors = {}
        password = request.form.get("password") or ""
        confirmation = request.form.get("password_confirmation") or ""
        validate_password(password, confirmation, errors)
        if errors:
            return render_template(
                "auth/reset.html", token=token, error=errors["password"]
            )

        record = PasswordResetToken.query.filter_by(token=token).first()
        user = User.query.filter_by(email=record.email).first()
        if user is None:
            db.session.delete(record)
            db.session.commit()
            flash("No se encontró la cuenta asociada.", "error")
            return redirect("/forgot-password")

        user.set_password(password)
        db.session.delete(record)
        db.session.commit()

        flash("Contraseña actualizada correctamente. Ya puedes iniciar sesión.", "success")
        return redirect("/login")

    if not _valid_token(token):
        return render_template("auth/reset.html", invalidToken=True)
    return render_template("auth/reset.html", token=token)


# ---------------------------------------------------------------------------
# Google OAuth2 (optional; enabled only when credentials are configured)
# ---------------------------------------------------------------------------
@bp.route("/auth/google")
def google_login():
    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    if not client_id:
        flash("El inicio de sesión con Google no está configurado.", "error")
        return redirect("/login")

    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    params = {
        "client_id": client_id,
        "redirect_uri": current_app.config.get("GOOGLE_REDIRECT_URI"),
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@bp.route("/login/oauth2/code/google")
def google_callback():
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or state != session.pop("oauth_state", None):
        return redirect("/login?error=true")

    data = urlencode(
        {
            "code": code,
            "client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
            "client_secret": current_app.config.get("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": current_app.config.get("GOOGLE_REDIRECT_URI"),
            "grant_type": "authorization_code",
        }
    ).encode()
    try:
        token_request = Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(token_request, timeout=15) as response:
            access_token = json.load(response)["access_token"]
        user_request = Request(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urlopen(user_request, timeout=15) as response:
            info = json.load(response)
    except Exception:
        return redirect("/login?error=true")

    email = (info.get("email") or "").strip().lower()
    if not email:
        return redirect("/login?error=true")

    user = User.query.filter_by(email=email).first()
    if user is None:
        role = Role.query.filter_by(name="CLIENTE").first()
        if role is None:
            role = Role(name="CLIENTE")
            db.session.add(role)
            db.session.flush()
        user = User(
            name=info.get("given_name") or info.get("name") or email.split("@")[0],
            last_name=info.get("family_name"),
            email=email,
            role=role,
            google_id=info.get("sub"),
            photo_url=info.get("picture"),
            enabled=True,
        )
        user.set_password(secrets.token_hex(24))
        db.session.add(user)
    else:
        user.google_id = info.get("sub") or user.google_id
        user.photo_url = info.get("picture") or user.photo_url
    db.session.commit()

    login_user(user, remember=True)
    return redirect("/dashboard")
