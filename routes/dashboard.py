"""Dashboard for administrators and clients (ported from DashboardController)."""

from datetime import date, timedelta

from flask import Blueprint, redirect, render_template
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Appointment, Inventory, LoyaltyCard, Service, User
from ..utils import format_currency, format_date_es

bp = Blueprint("dashboard", __name__)

DAYS_SHORT_ES = ["lun.", "mar.", "mié.", "jue.", "vie.", "sáb.", "dom."]


def _is_admin(user):
    return user.role is not None and (user.role.name or "").lower() == "admin"


@bp.route("/dashboard")
@login_required
def index():
    user = current_user
    if not _is_admin(user):
        return _client_dashboard(user)
    return _admin_dashboard(user)


def _admin_dashboard(user):
    today = date.today()
    all_appointments = Appointment.query.all()

    total_clients = User.query.all()
    total_clients = [u for u in total_clients if u.role is not None and (u.role.name or "").lower() != "admin"]

    total_appointments = len(all_appointments)
    today_appointments = [a for a in all_appointments if a.date is not None and a.date == today]
    realizada_status = ("confirmada", "completada")
    servicios_realizados = [a for a in all_appointments if (a.status or "").lower() in realizada_status]

    confirmadas = sum(1 for a in all_appointments if (a.status or "").lower() == "confirmada")
    pendientes = sum(1 for a in all_appointments if (a.status or "").lower() == "pendiente")
    canceladas = sum(1 for a in all_appointments if (a.status or "").lower() == "cancelada")

    citas_hoy_confirmadas = sum(1 for a in today_appointments if (a.status or "").lower() == "confirmada")
    citas_hoy_pendientes = sum(1 for a in today_appointments if (a.status or "").lower() == "pendiente")
    citas_hoy_canceladas = sum(1 for a in today_appointments if (a.status or "").lower() == "cancelada")

    start = today - timedelta(days=7)
    chart_days = [start + timedelta(days=i) for i in range(8)]
    by_day = {day: 0 for day in chart_days}
    for appointment in all_appointments:
        if appointment.date in by_day:
            by_day[appointment.date] += 1
    chart_counts = [by_day[day] for day in chart_days]
    chart_labels = [DAYS_SHORT_ES[day.weekday()] for day in chart_days]

    citas_semana_anterior = sum(
        1 for a in all_appointments if a.date is not None and a.date == today - timedelta(weeks=1)
    )
    citas_hoy = len(today_appointments)
    if citas_semana_anterior > 0:
        diff = citas_hoy - citas_semana_anterior
        pct = abs(diff) * 100 // citas_semana_anterior
        trend_up = diff >= 0
        trend_citas = ("+" if trend_up else "-") + str(pct) + "% vs hace una semana"
    else:
        trend_up = citas_hoy > 0
        trend_citas = "Nuevas citas hoy" if citas_hoy > 0 else "Sin cambios"

    total_ventas = sum(
        (a.service.price or 0) for a in servicios_realizados if a.service is not None
    )
    ticket_promedio = 0
    if servicios_realizados and total_ventas > 0:
        ticket_promedio = round(total_ventas / len(servicios_realizados))

    citas_hoy_list = sorted(today_appointments, key=lambda a: (a.time is None, a.time))
    if citas_hoy_list:
        ultimas_citas = citas_hoy_list
    else:
        ultimas_citas = Appointment.query.order_by(Appointment.date.desc(), Appointment.time.desc()).limit(5).all()

    productos_bajo_stock = (
        Inventory.query.filter(Inventory.stock <= Inventory.min_stock)
        .order_by(Inventory.stock.asc())
        .limit(5)
        .all()
    )

    servicios = Service.query.all()
    max_count = 1
    for service in servicios:
        count = sum(1 for a in all_appointments if a.service_id == service.id)
        if count > max_count:
            max_count = count
    servicios_populares = []
    for service in servicios[:5]:
        count = sum(1 for a in all_appointments if a.service_id == service.id)
        porcentaje = round(count * 100.0 / max_count)
        servicios_populares.append({"service": service, "count": count, "percentage": porcentaje})

    return render_template(
        "dashboard.html",
        currentUser=user,
        isAdmin=True,
        usuarios=len(total_clients),
        citas=total_appointments,
        servicios=Service.query.count(),
        productos=Inventory.query.count(),
        citasHoy=citas_hoy,
        serviciosRealizados=len(servicios_realizados),
        totalVentas=format_currency(total_ventas),
        ticketPromedio=format_currency(ticket_promedio),
        ultimasCitas=ultimas_citas,
        productosBajoStock=productos_bajo_stock,
        serviciosPopulares=servicios_populares,
        confirmadas=confirmadas,
        pendientes=pendientes,
        canceladas=canceladas,
        citasHoyConfirmadas=citas_hoy_confirmadas,
        citasHoyPendientes=citas_hoy_pendientes,
        citasHoyCanceladas=citas_hoy_canceladas,
        chartLabels=chart_labels,
        chartCounts=chart_counts,
        trendCitas=trend_citas,
        trendCitasUp=trend_up,
        fechaHoy=format_date_es(today, "d 'de' MMMM 'de' yyyy"),
    )


def _client_dashboard(user):
    mis_citas = (
        Appointment.query.filter_by(user_id=user.id)
        .order_by(Appointment.date.desc(), Appointment.time.desc())
        .all()
    )
    completadas = sum(1 for c in mis_citas if (c.status or "").lower() in ("confirmada", "completada"))

    today = date.today()
    proxima_cita = None
    candidates = [
        c for c in mis_citas
        if c.date is not None and c.date >= today and (c.status or "").lower() != "cancelada"
    ]
    if candidates:
        proxima_cita = min(candidates, key=lambda c: (c.date, c.time is None, c.time))

    card = LoyaltyCard.query.filter_by(user_id=user.id).first()
    if card is None:
        card = LoyaltyCard(user=user, stamps=0, available_rewards=0)
        db.session.add(card)
        db.session.commit()

    return render_template(
        "client/dashboard.html",
        currentUser=user,
        isAdmin=False,
        misCitas=mis_citas,
        totalCitas=len(mis_citas),
        citasCompletadas=completadas,
        proximaCita=proxima_cita,
        card=card,
        remainingStamps=max(0, 9 - card.stamps),
        visitas=completadas,
        servicios=Service.query.limit(6).all(),
    )
