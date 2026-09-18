from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models.report import FinalReport, ReportTable


class ReportGenerationError(Exception):
    """Raised when report generation fails."""


def generate_pdf(
    report: FinalReport,
    output_path: str | Path,
    include_checklist: bool = True,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        document = SimpleDocTemplate(
            str(output),
            pagesize=A4,
            title=f"{report.ticker or 'Company'} Analysis Report",
        )

        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(f"Stock Analysis Report: {report.company_name or report.ticker or 'Company'}", styles["Title"]))
        story.append(Paragraph(f"Ticker: {report.ticker or 'N/A'} | Status: {report.status}", styles["Normal"]))
        story.append(Paragraph(f"Generated at: {report.generated_at.isoformat(timespec='seconds')}", styles["Normal"]))
        story.append(Spacer(1, 8 * mm))

        story.append(Paragraph("Executive Summary", styles["Heading2"]))
        bullet_style = styles["List Bullet"] if "List Bullet" in styles else styles["BodyText"]

        for item in report.executive_summary:
            story.append(Paragraph(item, bullet_style))

        story.append(Spacer(1, 4 * mm))

        for section in report.sections:
            story.append(Paragraph(section.title, styles["Heading2"]))
            story.append(Paragraph(section.summary, styles["BodyText"]))

            for bullet in section.bullets:
                story.append(Paragraph(bullet, bullet_style))

            for table in section.tables:
                story.append(Spacer(1, 2 * mm))
                story.append(Paragraph(table.title, styles["Heading3"]))
                story.append(_build_table(table))

            story.append(Spacer(1, 4 * mm))

        if report.chart_paths:
            story.append(Paragraph("Technical Charts", styles["Heading2"]))

            for name, path in report.chart_paths.items():
                image_path = Path(path)

                if not image_path.exists():
                    continue

                story.append(Paragraph(name.replace("_", " ").title(), styles["Heading3"]))
                story.append(Image(str(image_path), width=170 * mm, height=100 * mm))
                story.append(Spacer(1, 3 * mm))

        if report.assumptions:
            story.append(Paragraph("Assumptions & Data Notes", styles["Heading2"]))

            for assumption in report.assumptions:
                story.append(Paragraph(assumption, bullet_style))

        if include_checklist and report.checklist:
            story.append(Paragraph("227-Point Checklist Appendix", styles["Heading2"]))

            checklist_rows = [["Item", "Section", "Description", "Module", "Status"]]

            for item in report.checklist:
                checklist_rows.append([item.item_id, item.section, item.description, item.module, item.status])

            checklist_table = Table(checklist_rows, repeatRows=1)
            checklist_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3864")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )

            story.append(checklist_table)

        document.build(story)
        return output
    except Exception as exc:
        raise ReportGenerationError(f"Failed to generate PDF report: {output}") from exc


def _build_table(table: ReportTable) -> Table:
    data = [table.headers]

    for row in table.rows:
        data.append(["" if cell is None else str(cell) for cell in row])

    built = Table(data, repeatRows=1)
    built.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e5d8c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    return built
