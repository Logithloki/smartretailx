"""Order Summary PDF generator using fpdf2.

Produces a clean, professional document with order metadata, line items,
and pricing breakdown. Deliberately avoids payment/invoice/receipt semantics.
"""

from __future__ import annotations

import io
from decimal import Decimal

from fpdf import FPDF

from .models import Order


def _fmt(value: Decimal | str) -> str:
    d = Decimal(str(value))
    return f"£{d:,.2f}"


def generate_order_summary(order: Order) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "SmartRetailX", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "Order Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(8)

    # Order metadata
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(35, 6, "Order ID:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, order.orderId, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(35, 6, "Date:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, order.createdAt.strftime("%d %B %Y, %H:%M UTC"), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(35, 6, "Status:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, order.status.value, new_x="LMARGIN", new_y="NEXT")

    if order.fulfilmentStatus.value != "NOT_STARTED":
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(35, 6, "Fulfilment:")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, order.fulfilmentStatus.value.replace("_", " "), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)

    # Divider
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    # Line items table header
    col_widths = [70, 15, 25, 25, 25, 30]
    headers = ["Product", "Qty", "Unit Price", "Effective", "Discount", "Line Total"]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(245, 245, 245)
    for i, header in enumerate(headers):
        align = "L" if i == 0 else "R"
        pdf.cell(col_widths[i], 8, header, border=0, fill=True, align=align)
    pdf.ln()

    # Line items
    pdf.set_font("Helvetica", "", 9)
    for item in order.items:
        name = item.productName or item.productId
        if len(name) > 35:
            name = name[:32] + "..."
        pdf.cell(col_widths[0], 7, name, align="L")
        pdf.cell(col_widths[1], 7, str(item.quantity), align="R")
        pdf.cell(col_widths[2], 7, _fmt(item.baseUnitPrice), align="R")
        pdf.cell(col_widths[3], 7, _fmt(item.effectiveUnitPrice), align="R")
        pdf.cell(col_widths[4], 7, _fmt(item.lineDiscount), align="R")
        pdf.cell(col_widths[5], 7, _fmt(item.lineTotal), align="R")
        pdf.ln()

        if item.promotionId:
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(col_widths[0], 5, f"  Promotion: {item.promotionId}")
            pdf.ln()
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(0, 0, 0)

    pdf.ln(4)

    # Divider
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    # Totals
    totals_x = 130
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(totals_x)
    pdf.cell(35, 7, "Subtotal:", align="R")
    pdf.cell(25, 7, _fmt(order.subtotal), align="R")
    pdf.ln()

    if order.discountTotal > 0:
        pdf.set_x(totals_x)
        pdf.cell(35, 7, "Discount:", align="R")
        pdf.set_text_color(0, 128, 0)
        pdf.cell(25, 7, f"-{_fmt(order.discountTotal)}", align="R")
        pdf.set_text_color(0, 0, 0)
        pdf.ln()

    pdf.set_x(totals_x)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(35, 8, "Order Total:", align="R")
    pdf.cell(25, 8, _fmt(order.totalAmount), align="R")
    pdf.ln()

    if order.statusReason:
        pdf.ln(6)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(150, 50, 50)
        pdf.cell(0, 6, f"Note: {order.statusReason}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    # Footer
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, "This is an order summary, not a tax invoice or payment receipt.", align="C")

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
