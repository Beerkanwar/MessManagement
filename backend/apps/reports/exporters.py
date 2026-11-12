"""
Export writers for Phase 12 reports.

All three formats share the registry's primary column set.  Totals and grouped
summaries are emitted as separate sections/sheets so screens and files agree.

CSV
    UTF-8 with BOM, cells beginning with =, +, - or @ neutralised.

XLSX
    Write-only streaming workbook, typed numeric/date cells, frozen header and
    a rupee number format.

PDF
    A4 landscape, repeating header, page numbers, metadata and totals.  The
    bundled DejaVu fonts contain the Indian rupee sign (U+20B9).
"""
from __future__ import annotations

import csv
import html
import io
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.reports.registry import ReportColumn, ReportDefinition

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT_REGULAR_PATH = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD_PATH = FONT_DIR / "DejaVuSans-Bold.ttf"
PDF_FONT = "DejaVuSans"
PDF_FONT_BOLD = "DejaVuSans-Bold"
MONEY_FORMAT = '"₹"#,##0.00'
DATE_FORMAT = "yyyy-mm-dd"


def _register_pdf_fonts() -> None:
    registered = set(pdfmetrics.getRegisteredFontNames())
    if PDF_FONT not in registered:
        pdfmetrics.registerFont(TTFont(PDF_FONT, str(FONT_REGULAR_PATH)))
    if PDF_FONT_BOLD not in registered:
        pdfmetrics.registerFont(TTFont(PDF_FONT_BOLD, str(FONT_BOLD_PATH)))


def _human_label(key: str) -> str:
    return key.replace("_", " ").strip().title()


def _money(value: Any) -> str:
    amount = value if isinstance(value, Decimal) else Decimal(str(value or 0))
    return f"₹{amount:,.2f}"


def _format_value(value: Any, column: ReportColumn | None = None) -> str:
    if value is None:
        return ""
    if column is not None and column.money:
        return _money(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Decimal):
        return f"{value:.2f}" if column and column.kind == "decimal" else str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if column is not None and column.kind == "int":
        return str(value)
    return str(value)


def _neutralize_csv_cell(value: Any) -> Any:
    """Neutralises spreadsheet formulas without mangling numeric negatives."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _neutralize_csv_cell(value)
    return value


def _project_rows(
    definition: ReportDefinition, rows: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    keys = definition.column_keys
    return [{key: row.get(key) for key in keys} for row in rows]


def _total_rows(
    definition: ReportDefinition, totals: dict[str, Any]
) -> list[tuple[str, Any, ReportColumn | None]]:
    return [
        (
            _totals_column(definition, key).label
            if _totals_column(definition, key)
            else _human_label(key),
            value,
            _totals_column(definition, key),
        )
        for key, value in totals.items()
    ]


def _totals_column(definition: ReportDefinition, key: str) -> ReportColumn | None:
    for column in definition.total_columns:
        if column.key == key:
            return column
    for column in definition.columns:
        if column.key == key:
            return column
    return None


def render_csv(
    definition: ReportDefinition,
    rows: Iterable[dict[str, Any]],
    totals: dict[str, Any],
    groups: list[dict[str, Any]],
) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")

    writer.writerow([column.label for column in definition.columns])
    for row in _project_rows(definition, rows):
        writer.writerow(
            [_csv_value(row.get(column.key)) for column in definition.columns]
        )

    if totals:
        writer.writerow([])
        writer.writerow(["Totals"])
        for label, value, _column in _total_rows(definition, totals):
            writer.writerow([label, _csv_value(value)])

    if groups:
        writer.writerow([])
        writer.writerow(["Groups"])
        group_keys = list(groups[0].keys())
        writer.writerow([_human_label(key) for key in group_keys])
        for group in groups:
            writer.writerow([_csv_value(group.get(key)) for key in group_keys])

    return buffer.getvalue().encode("utf-8-sig")


def _xlsx_cell(ws, value: Any, column: ReportColumn):
    if isinstance(value, Decimal):
        value = float(value)
    cell = WriteOnlyCell(ws, value=value)
    if column.money:
        cell.number_format = MONEY_FORMAT
    elif column.kind == "int":
        cell.number_format = "#,##0"
    elif column.kind == "decimal":
        cell.number_format = "#,##0.00"
    elif column.kind == "date" and isinstance(value, (date, datetime)):
        cell.number_format = DATE_FORMAT
    if column.kind in ("text", "month") and isinstance(value, str):
        cell.alignment = Alignment(vertical="top", wrap_text=False)
    return cell


def _write_sheet_rows(ws, definition: ReportDefinition, rows: list[dict[str, Any]]):
    header_cells = []
    for index, column in enumerate(definition.columns, start=1):
        cell = WriteOnlyCell(ws, value=column.label)
        cell.font = Font(name="Calibri", bold=True)
        cell.fill = PatternFill("solid", fgColor="DDEBF7")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        header_cells.append(cell)
        ws.column_dimensions[get_column_letter(index)].width = max(
            12, min(40, len(column.label) + 4)
        )
    # Write-only worksheets serialise their sheet view with the first append,
    # so the freeze pane must be set before the header row is written.
    ws.freeze_panes = "A2"
    ws.append(header_cells)

    for row in rows:
        ws.append(
            [
                _xlsx_cell(ws, row.get(column.key), column)
                for column in definition.columns
            ]
        )


def _write_key_value_sheet(
    ws, title: str, pairs: list[tuple[str, Any, ReportColumn | None]]
):
    title_cell = WriteOnlyCell(ws, value=title)
    title_cell.font = Font(name="Calibri", bold=True, size=13)
    ws.append([title_cell])
    header = [WriteOnlyCell(ws, value="Measure"), WriteOnlyCell(ws, value="Value")]
    for cell in header:
        cell.font = Font(name="Calibri", bold=True)
    ws.append(header)
    for label, value, column in pairs:
        if column is None:
            value_cell = WriteOnlyCell(
                ws, value=float(value) if isinstance(value, Decimal) else value
            )
        else:
            value_cell = _xlsx_cell(ws, value, column)
        ws.append([label, value_cell])


def render_xlsx(
    definition: ReportDefinition,
    rows: Iterable[dict[str, Any]],
    totals: dict[str, Any],
    groups: list[dict[str, Any]],
) -> bytes:
    projected = _project_rows(definition, rows)
    workbook = Workbook(write_only=True)
    data_sheet = workbook.create_sheet("Data")
    _write_sheet_rows(data_sheet, definition, projected)

    if totals:
        totals_sheet = workbook.create_sheet("Totals")
        _write_key_value_sheet(
            totals_sheet, "Totals", _total_rows(definition, totals)
        )

    if groups:
        groups_sheet = workbook.create_sheet("Groups")
        group_keys = list(groups[0].keys())
        header = [
            WriteOnlyCell(groups_sheet, value=_human_label(key))
            for key in group_keys
        ]
        for cell in header:
            cell.font = Font(name="Calibri", bold=True)
        groups_sheet.append(header)
        for group in groups:
            groups_sheet.append(
                [
                    float(group[key]) if isinstance(group[key], Decimal) else group[key]
                    for key in group_keys
                ]
            )

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def _pdf_cell(value: Any, column: ReportColumn) -> str:
    if value is None:
        return ""
    if column.money:
        return _money(value)
    if isinstance(value, Decimal):
        return f"{value:.2f}" if column.kind == "decimal" else str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if column.kind == "int":
        return f"{int(value):,}"
    return str(value)


def _pdf_table(
    definition: ReportDefinition,
    rows: list[dict[str, Any]],
    available_width: float,
) -> Table:
    data = [[column.label for column in definition.columns]]
    for row in rows:
        data.append(
            [
                _pdf_cell(row.get(column.key), column)
                for column in definition.columns
            ]
        )

    count = max(1, len(definition.columns))
    col_width = available_width / count
    table = Table(
        data,
        colWidths=[col_width] * count,
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), PDF_FONT),
                ("FONTNAME", (0, 0), (-1, 0), PDF_FONT_BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEBF7")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9AA7B4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FB")]),
            ]
        )
    )
    return table


def _pdf_key_value_table(
    definition: ReportDefinition,
    pairs: list[tuple[str, Any, ReportColumn | None]],
    available_width: float,
) -> Table:
    data = []
    for label, value, column in pairs:
        data.append([label, _format_value(value, column)])
    table = Table(data, colWidths=[available_width * 0.35, available_width * 0.65])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), PDF_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9AA7B4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def render_pdf(
    definition: ReportDefinition,
    rows: Iterable[dict[str, Any]],
    totals: dict[str, Any],
    groups: list[dict[str, Any]],
    *,
    scope_label: str,
    date_from: date,
    date_to: date,
    generated_by: str,
    generated_at_ist: str,
) -> bytes:
    _register_pdf_fonts()
    projected = _project_rows(definition, rows)
    output = io.BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        output,
        pagesize=page_size,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=14 * mm,
        title=definition.title,
        author="Hostel Mess Management System",
    )
    available_width = page_size[0] - 20 * mm

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName=PDF_FONT_BOLD,
        fontSize=16,
        leading=20,
        alignment=TA_LEFT,
    )
    meta_style = ParagraphStyle(
        "ReportMeta",
        parent=styles["Normal"],
        fontName=PDF_FONT,
        fontSize=8.5,
        leading=12,
        alignment=TA_LEFT,
    )
    section_style = ParagraphStyle(
        "ReportSection",
        parent=styles["Heading2"],
        fontName=PDF_FONT_BOLD,
        fontSize=11,
        leading=14,
        spaceBefore=8,
        spaceAfter=4,
        alignment=TA_LEFT,
    )

    story = [
        Paragraph(html.escape(definition.title), title_style),
        Paragraph(
            "Scope: " + html.escape(scope_label),
            meta_style,
        ),
        Paragraph(
            f"Range: {date_from.isoformat()} to {date_to.isoformat()}",
            meta_style,
        ),
        Paragraph("Generated by: " + html.escape(generated_by), meta_style),
        Paragraph("Generated at (IST): " + html.escape(generated_at_ist), meta_style),
        Spacer(1, 6),
        _pdf_table(definition, projected, available_width),
    ]

    if totals:
        story.append(Paragraph("Totals", section_style))
        story.append(
            _pdf_key_value_table(
                definition, _total_rows(definition, totals), available_width
            )
        )

    if groups:
        story.append(Paragraph("Groups", section_style))
        group_keys = list(groups[0].keys())
        header = [_human_label(key) for key in group_keys]
        data = [header]
        for group in groups:
            data.append(
                [
                    _format_value(
                        group.get(key), _totals_column(definition, key)
                    )
                    for key in group_keys
                ]
            )
        group_table = Table(
            data,
            colWidths=[available_width / max(1, len(header))] * max(1, len(header)),
            repeatRows=1,
        )
        group_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), PDF_FONT),
                    ("FONTNAME", (0, 0), (-1, 0), PDF_FONT_BOLD),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEBF7")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9AA7B4")),
                ]
            )
        )
        story.append(group_table)

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont(PDF_FONT, 7.5)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(10 * mm, 6 * mm, definition.title)
        canvas.drawCentredString(
            page_size[0] / 2, 6 * mm, f"Page {doc_.page}"
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return output.getvalue()
