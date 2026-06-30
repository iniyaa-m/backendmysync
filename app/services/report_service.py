import io
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.analytics.analytics_service import get_student_analytics
from app.utils.logger import logger


async def generate_pdf_report(db: AsyncIOMotorDatabase, user_id: str, user_name: str, period: str = "weekly") -> bytes:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.units import inch

        analytics = await get_student_analytics(db, user_id, period)
        summary = analytics.get("summary", {})
        insights = analytics.get("insights", [])

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=20, textColor=colors.HexColor("#7c3aed"), spaceAfter=6)
        heading_style = ParagraphStyle("Heading", parent=styles["Heading2"], fontSize=14, textColor=colors.HexColor("#1e293b"), spaceAfter=4)
        body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=11, spaceAfter=4)

        elements = []
        elements.append(Paragraph("MindSync AI Classroom", title_style))
        elements.append(Paragraph(f"{period.capitalize()} Learning Report — {user_name}", heading_style))
        elements.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y %H:%M')}", body_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#7c3aed")))
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph("Performance Summary", heading_style))
        table_data = [
            ["Metric", "Value"],
            ["Average Focus Score", f"{summary.get('avg_focus', 0):.1f}%"],
            ["Average Stress Score", f"{summary.get('avg_stress', 0):.1f}%"],
            ["Total Study Time", f"{summary.get('total_study_minutes', 0) // 60}h {summary.get('total_study_minutes', 0) % 60}m"],
            ["Average Quiz Score", f"{summary.get('avg_quiz_score', 0):.1f}%"],
            ["Quizzes Taken", str(summary.get("total_quizzes", 0))],
            ["Dominant Emotion", summary.get("dominant_emotion", "N/A").capitalize()],
        ]
        table = Table(table_data, colWidths=[3.5*inch, 2.5*inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c3aed")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.3*inch))
        if insights:
            elements.append(Paragraph("AI Insights & Recommendations", heading_style))
            for insight in insights:
                elements.append(Paragraph(f"- {insight}", body_style))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
        elements.append(Paragraph("MindSync AI Classroom — Powered by AI for Personalized Learning", body_style))
        doc.build(elements)
        return buf.getvalue()
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        return b"%PDF-1.4 report generation failed"


async def generate_csv_report(db: AsyncIOMotorDatabase, user_id: str, period: str = "weekly") -> str:
    import csv
    import io as _io
    analytics = await get_student_analytics(db, user_id, period)
    data_points = analytics.get("data_points", [])
    output = _io.StringIO()
    if data_points:
        writer = csv.DictWriter(output, fieldnames=data_points[0].keys())
        writer.writeheader()
        writer.writerows(data_points)
    return output.getvalue()
