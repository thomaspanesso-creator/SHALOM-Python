"""Admin reports and the template-method export endpoint."""

from flask import Blueprint, Response, render_template, request

from ..decorators import admin_required
from ..models import Appointment, Inventory, Service

bp = Blueprint("reports", __name__)


@bp.route("/reportes/citas")
@admin_required
def citas():
    appointments = Appointment.query.order_by(Appointment.date.desc(), Appointment.time.desc()).all()
    return render_template("reportes/citas.html", citas=appointments)


@bp.route("/reportes/especialistas")
@admin_required
def especialistas():
    counts = {}
    for appointment in Appointment.query.all():
        key = appointment.worker or "Sin asignar"
        counts[key] = counts.get(key, 0) + 1
    rows = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return render_template("reportes/especialistas.html", especialistas=rows)


@bp.route("/reportes/ingresos")
@admin_required
def ingresos():
    citas_confirmadas = [
        a for a in Appointment.query.all()
        if (a.status or "").lower() in ("confirmada", "completada")
    ]
    total = sum((a.service.price or 0) for a in citas_confirmadas if a.service is not None)
    return render_template("reportes/ingresos.html", ingresos=total, citas=citas_confirmadas)


@bp.route("/reportes/inventario-bajo")
@admin_required
def inventario_bajo():
    productos = (
        Inventory.query.filter(Inventory.stock <= Inventory.min_stock)
        .order_by(Inventory.stock.asc())
        .all()
    )
    return render_template("reportes/inventario-bajo.html", productos=productos)


@bp.route("/reportes/servicios")
@admin_required
def servicios():
    counts = {}
    for appointment in Appointment.query.all():
        if appointment.service is not None:
            counts[appointment.service.name] = counts.get(appointment.service.name, 0) + 1
    rows = [
        {"service": name, "total": total}
        for name, total in sorted(counts.items(), key=lambda item: item[1], reverse=True)
    ]
    return render_template("reportes/servicios.html", servicioCounts=rows)


# ---------------------------------------------------------------------------
# Template Method pattern, as in the original ReporteController.
# ---------------------------------------------------------------------------
class ReportTemplate:
    def generate_report(self, title, data):
        parts = [
            self.initialize_document(),
            self.build_header(title),
            self.build_body(data),
            self.finalize_document(),
        ]
        return "".join(parts).encode("utf-8")

    def initialize_document(self):
        raise NotImplementedError

    def build_header(self, title):
        raise NotImplementedError

    def build_body(self, data):
        raise NotImplementedError

    def finalize_document(self):
        raise NotImplementedError


class PdfReportGenerator(ReportTemplate):
    def initialize_document(self):
        return "[PDF Inicializado]\n"

    def build_header(self, title):
        return f"[Encabezado PDF: {title}]\n"

    def build_body(self, data):
        return "[Cuerpo PDF: Dibujando tablas y celdas estilizadas]\n"

    def finalize_document(self):
        return "[PDF Cerrado y Guardado]\n"


class ExcelReportGenerator(ReportTemplate):
    def initialize_document(self):
        return "[Excel Inicializado (Workbook)]\n"

    def build_header(self, title):
        return f"[Fila 1 Excel - Título: {title}]\n"

    def build_body(self, data):
        return "[Cuerpo Excel: Insertando datos en filas y columnas de celdas]\n"

    def finalize_document(self):
        return "[Excel Autoajustado y Guardado]\n"


@bp.route("/api/reportes/ventas")
@admin_required
def download_sales_report():
    report_format = (request.args.get("format") or "").lower()
    generator = None
    mimetype = None
    extension = None

    if report_format == "pdf":
        generator = PdfReportGenerator()
        mimetype = "application/pdf"
        extension = ".pdf"
    elif report_format == "excel":
        generator = ExcelReportGenerator()
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        extension = ".xlsx"
    else:
        return Response(status=400)

    content = generator.generate_report("Reporte de Ventas Shalom", [{"id": 1, "monto": 150.0}])
    return Response(
        content,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="reporte_ventas{extension}"'},
    )
