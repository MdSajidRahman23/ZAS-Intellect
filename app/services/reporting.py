from __future__ import annotations

import csv
import os
from io import BytesIO, StringIO
from pathlib import Path
from textwrap import shorten
from sqlalchemy.orm import Session
from app.models.database import VivaSession, Submission, User
from app.services.scoring import proctor_risk_score
from app.services.proctoring import integrity_recommendation


def _fmt_dt(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()
    if text.lstrip()[:1] in {"=", "+", "-", "@"}:
        return "'" + text
    return text


def sessions_csv(db: Session, teacher: User | None = None, scope_mode: str = "all") -> str:
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "Session ID", "Status", "Student ID", "Student Name", "Student Email", "Course", "Assignment", "Group Code", "File",
        "AI Provider", "Adaptive Viva", "Submission Quality", "Viva Performance", "ZAS Score", "Proctor Risk", "Flag", "Teacher Decision",
        "Started", "Ended", "Completed Reason", "Video Chunks", "Critical Events", "Integrity Recommendation", "Feedback Summary"
    ])
    query = (
        db.query(VivaSession, Submission, User)
        .join(Submission, Submission.id == VivaSession.submission_id)
        .join(User, User.id == VivaSession.student_id)
    )
    if teacher is not None and scope_mode == "department":
        query = query.filter(User.department == teacher.department)
    rows = query.order_by(VivaSession.started_at.desc()).all()
    for session, submission, user in rows:
        live_proctor = proctor_risk_score([{"risk_weight": event.risk_weight} for event in session.proctor_events])
        critical_events = len([event for event in session.proctor_events if event.risk_weight >= 80])
        recommendation = integrity_recommendation(session.proctor_events, session.zas_score, live_proctor)
        writer.writerow([_csv_safe(v) for v in [
            session.id,
            session.status,
            user.identifier,
            user.name,
            user.email,
            submission.course_code,
            submission.assignment_title,
            submission.group_code,
            submission.original_filename,
            session.ai_provider_used or submission.ai_provider_used,
            "Score-based difficulty",
            f"{session.submission_quality:.2f}",
            f"{session.viva_performance:.2f}",
            f"{session.zas_score:.2f}",
            f"{live_proctor:.2f}",
            session.risk_flag,
            session.decision_status,
            _fmt_dt(session.started_at),
            _fmt_dt(session.ended_at),
            session.completed_reason,
            len(session.video_chunks),
            critical_events,
            recommendation,
            session.feedback_summary,
        ]])
    return "\ufeff" + output.getvalue()


def _register_pdf_fonts() -> tuple[str, str]:
    """Register a Unicode/Bangla-capable font when it exists on the host OS.

    No font files are bundled. On Windows this will usually use Nirmala UI or Vrinda;
    on Linux it uses Noto/Lohit Bengali when installed. Helvetica is the fallback.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates_regular = [
        os.getenv("ZAS_PDF_FONT_REGULAR", ""),
        r"C:\Windows\Fonts\Nirmala.ttf",
        r"C:\Windows\Fonts\Vrinda.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-bengali/Lohit-Bengali.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    candidates_bold = [
        os.getenv("ZAS_PDF_FONT_BOLD", ""),
        r"C:\Windows\Fonts\NirmalaB.ttf",
        r"C:\Windows\Fonts\Vrindab.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]

    regular = next((p for p in candidates_regular if p and Path(p).exists()), "")
    bold = next((p for p in candidates_bold if p and Path(p).exists()), "")
    if regular:
        try:
            pdfmetrics.registerFont(TTFont("ZASUnicode", regular))
            if bold:
                pdfmetrics.registerFont(TTFont("ZASUnicodeBold", bold))
                return "ZASUnicode", "ZASUnicodeBold"
            return "ZASUnicode", "ZASUnicode"
        except Exception:
            pass
    return "Helvetica", "Helvetica-Bold"


def _short(value: str, width: int = 700) -> str:
    return shorten(str(value or ""), width=width, placeholder="...")


def session_pdf(session: VivaSession, user: User) -> bytes:
    """Create a compact Unicode-friendly PDF report for teacher/student review."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors

    font_regular, font_bold = _register_pdf_fonts()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    for name in ["Normal", "BodyText", "Title", "Heading1", "Heading2", "Heading3"]:
        styles[name].fontName = font_bold if name in {"Title", "Heading1", "Heading2", "Heading3"} else font_regular
    styles.add(ParagraphStyle(name="SmallZAS", parent=styles["BodyText"], fontName=font_regular, fontSize=8, leading=10))
    story = []

    story.append(Paragraph("ZAS-Intellect Viva Integrity Report", styles["Title"]))
    story.append(Paragraph("Daffodil International University BLC · AI Project Competition 2026", styles["Normal"]))
    story.append(Spacer(1, 12))

    rows = [
        ["Student", f"{session.submission.student.name} ({session.submission.student.identifier})"],
        ["Course", session.submission.course_code],
        ["Assignment", session.submission.assignment_title],
        ["Group Code", session.submission.group_code or "Individual"],
        ["Status", session.status],
        ["ZAS Score", f"{session.zas_score:.2f}"],
        ["Viva Performance", f"{session.viva_performance:.2f}"],
        ["Submission Quality", f"{session.submission_quality:.2f}"],
        ["Proctor Risk", f"{session.proctor_risk:.2f}"],
        ["Video Evidence Chunks", str(len(session.video_chunks))],
        ["Critical Proctor Events", str(len([e for e in session.proctor_events if e.risk_weight >= 80]))],
        ["Flag", session.risk_flag],
        ["Teacher Decision", session.decision_status],
        ["AI Provider", session.ai_provider_used or session.submission.ai_provider_used or "offline"],
        ["Adaptive Viva", "Score-based difficulty: strong answers raise level; weak answers lower level"],
    ]
    table = Table(rows, colWidths=[120, 360])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF5F0")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C7C0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), font_regular),
        ("FONTNAME", (0, 0), (0, -1), font_bold),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph("Feedback Summary", styles["Heading2"]))
    story.append(Paragraph(_short(session.feedback_summary or "No feedback generated yet."), styles["BodyText"]))
    story.append(Paragraph("Integrity Recommendation", styles["Heading2"]))
    story.append(Paragraph(_short(integrity_recommendation(session.proctor_events, session.zas_score, session.proctor_risk), 700), styles["BodyText"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Proctoring Timeline", styles["Heading2"]))
    for event in sorted(session.proctor_events, key=lambda item: item.created_at)[:30]:
        story.append(Paragraph(f"{_fmt_dt(event.created_at)} · {event.event_type} · Risk +{event.risk_weight:.1f}", styles["SmallZAS"]))
        story.append(Paragraph(_short(event.details, 450), styles["SmallZAS"]))
    if len(session.proctor_events) > 30:
        story.append(Paragraph(f"... and {len(session.proctor_events) - 30} more events", styles["SmallZAS"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Question Transcript", styles["Heading2"]))
    for q in sorted(session.questions, key=lambda item: item.q_order):
        story.append(Paragraph(f"Q{q.q_order} · {q.category} · {q.difficulty_label} · Official {q.answer_score:.1f} (Raw {(q.raw_score or q.answer_score):.1f})", styles["Heading3"]))
        story.append(Paragraph(_short(q.question or "", 650), styles["BodyText"]))
        if getattr(q, "adaptive_note", ""):
            story.append(Paragraph("Adaptive note: " + _short(q.adaptive_note, 500), styles["SmallZAS"]))
        if q.answer:
            story.append(Paragraph("Answer: " + _short(q.answer, 850), styles["BodyText"]))
        if q.feedback:
            story.append(Paragraph("Feedback: " + _short(q.feedback, 650), styles["BodyText"]))
        story.append(Spacer(1, 6))

    doc.build(story)
    return buffer.getvalue()
