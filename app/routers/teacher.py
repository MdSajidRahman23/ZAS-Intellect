from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import audit_log, csrf_token, require_role, validate_csrf
from app.models.database import Submission, User, VideoChunk, VivaSession
from app.services.reporting import session_pdf, sessions_csv
from app.services.scoring import proctor_risk_score
from app.services.session_manager import expire_overdue_sessions
from app.core.time_utils import utc_now
from app.services.ai_engine import ai_engine
from app.services.proctoring import integrity_recommendation

router = APIRouter(prefix="/teacher")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["csrf_token"] = csrf_token
settings = get_settings()
templates.env.globals["settings"] = settings

VALID_FLAGS = {"all", "pending", "high", "borderline", "proctor", "security", "passed", "in_progress", "completed", "needs_action"}
FLAG_MAP = {
    "pending": "Pending",
    "high": "High Discrepancy",
    "borderline": "Borderline Review",
    "proctor": "Proctor Review",
    "passed": "Passed",
    "security": "Security Violation",
}
VALID_DECISIONS = {"Pending Teacher Review", "Accepted", "Needs Physical Viva", "Penalized", "Recheck Required", "Rejected: Secure Violation"}


def _attach_live_proctor(session: VivaSession) -> VivaSession:
    live = proctor_risk_score([{"risk_weight": event.risk_weight} for event in session.proctor_events])
    session.live_proctor_risk = live
    return session


@router.get("")
def dashboard(
    request: Request,
    flag: str = Query("all"),
    q: str = Query(""),
    user: User = Depends(require_role("teacher")),
    db: Session = Depends(get_db),
):
    expire_overdue_sessions(db)
    flag = flag if flag in VALID_FLAGS else "all"
    query = (
        db.query(VivaSession)
        .join(Submission, Submission.id == VivaSession.submission_id)
        .join(User, User.id == VivaSession.student_id)
        .order_by(VivaSession.started_at.desc())
    )
    if settings.teacher_scope_mode == "department":
        query = query.filter(User.department == user.department)

    search = q.strip()
    if search:
        like = f"%{search}%"
        query = query.filter(or_(
            User.name.ilike(like),
            User.identifier.ilike(like),
            Submission.course_code.ilike(like),
            Submission.assignment_title.ilike(like),
            Submission.group_code.ilike(like),
        ))

    if flag in FLAG_MAP:
        query = query.filter(VivaSession.risk_flag == FLAG_MAP[flag])
    elif flag in {"in_progress", "completed"}:
        query = query.filter(VivaSession.status == flag)
    elif flag == "needs_action":
        query = query.filter(VivaSession.decision_status.in_(["Pending Teacher Review", "Needs Physical Viva", "Recheck Required"]))

    sessions = [_attach_live_proctor(session) for session in query.all()]
    all_sessions_query = db.query(VivaSession).join(User, User.id == VivaSession.student_id)
    if settings.teacher_scope_mode == "department":
        all_sessions_query = all_sessions_query.filter(User.department == user.department)
    all_sessions = all_sessions_query.all()
    total = len(all_sessions)
    high = len([s for s in all_sessions if s.risk_flag == "High Discrepancy"])
    security = len([s for s in all_sessions if s.risk_flag == "Security Violation"])
    borderline = len([s for s in all_sessions if s.risk_flag == "Borderline Review"])
    in_progress = len([s for s in all_sessions if s.status == "in_progress"])
    completed = len([s for s in all_sessions if s.status == "completed"])
    avg_zas = round(sum(s.zas_score for s in all_sessions if s.status == "completed") / max(1, completed), 2)
    return templates.TemplateResponse(request, "teacher_dashboard.html", {
        "request": request,
        "user": user,
        "sessions": sessions,
        "total": total,
        "high": high,
        "borderline": borderline,
        "security": security,
        "in_progress": in_progress,
        "avg_zas": avg_zas,
        "selected_flag": flag,
        "search": search,
        "ai_status": ai_engine.provider_status(),
        "teacher_scope": settings.teacher_scope_mode,
    })


@router.get("/session/{session_id}")
def session_detail(request: Request, session_id: int, user: User = Depends(require_role("teacher")), db: Session = Depends(get_db)):
    expire_overdue_sessions(db)
    session = db.get(VivaSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if settings.teacher_scope_mode == "department" and session.submission.student.department != user.department:
        raise HTTPException(status_code=403, detail="This session is outside your teacher scope")
    _attach_live_proctor(session)
    recommendation = integrity_recommendation(session.proctor_events, session.zas_score, session.live_proctor_risk)
    return templates.TemplateResponse(request, "teacher_session.html", {"request": request, "user": user, "session": session, "decisions": sorted(VALID_DECISIONS), "ai_status": ai_engine.provider_status(), "integrity_recommendation": recommendation})


@router.post("/session/{session_id}/decision")
def teacher_decision(
    request: Request,
    session_id: int,
    decision_status: str = Form(...),
    decision_note: str = Form(""),
    csrf_token: str = Form(...),
    user: User = Depends(require_role("teacher")),
    db: Session = Depends(get_db),
):
    validate_csrf(request, csrf_token)
    expire_overdue_sessions(db)
    session = db.get(VivaSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if settings.teacher_scope_mode == "department" and session.submission.student.department != user.department:
        raise HTTPException(status_code=403, detail="This session is outside your teacher scope")
    if decision_status not in VALID_DECISIONS:
        raise HTTPException(status_code=400, detail="Invalid teacher decision")
    session.decision_status = decision_status
    session.decision_note = decision_note.strip()[:2000]
    session.decided_by = user.id
    session.decided_at = utc_now()
    audit_log(db, request, user.id, "teacher_decision_updated", f"session_id={session.id}; decision={decision_status}")
    db.commit()
    return RedirectResponse(f"/teacher/session/{session.id}", status_code=303)


@router.get("/session/{session_id}/report.pdf")
def teacher_report_pdf(request: Request, session_id: int, user: User = Depends(require_role("teacher")), db: Session = Depends(get_db)):
    expire_overdue_sessions(db)
    session = db.get(VivaSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if settings.teacher_scope_mode == "department" and session.submission.student.department != user.department:
        raise HTTPException(status_code=403, detail="This session is outside your teacher scope")
    pdf = session_pdf(session, user)
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=zas_report_session_{session.id}.pdf"})


@router.get("/session/{session_id}/video/{chunk_id}")
def teacher_video_chunk(session_id: int, chunk_id: int, user: User = Depends(require_role("teacher")), db: Session = Depends(get_db)):
    session = db.get(VivaSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if settings.teacher_scope_mode == "department" and session.submission.student.department != user.department:
        raise HTTPException(status_code=403, detail="This session is outside your teacher scope")
    chunk = db.get(VideoChunk, chunk_id)
    if not chunk or chunk.session_id != session.id:
        raise HTTPException(status_code=404, detail="Video evidence not found")
    path = chunk.stored_path
    return FileResponse(path, media_type=chunk.mime_type or "video/webm", filename=f"zas_session_{session.id}_chunk_{chunk.chunk_index}.webm")


@router.get("/group")
def group_fairness(request: Request, code: str = Query(""), user: User = Depends(require_role("teacher")), db: Session = Depends(get_db)):
    group_code = code.strip()
    if not group_code:
        raise HTTPException(status_code=400, detail="Group code is required")
    query = (
        db.query(VivaSession)
        .join(Submission, Submission.id == VivaSession.submission_id)
        .join(User, User.id == VivaSession.student_id)
        .filter(Submission.group_code == group_code)
    )
    if settings.teacher_scope_mode == "department":
        query = query.filter(User.department == user.department)
    sessions = query.order_by(VivaSession.zas_score.desc()).all()
    sessions = [_attach_live_proctor(session) for session in sessions]
    return templates.TemplateResponse(request, "group_fairness.html", {"request": request, "user": user, "group_code": group_code, "sessions": sessions})


@router.get("/export.csv")
def export_csv(user: User = Depends(require_role("teacher")), db: Session = Depends(get_db)):
    expire_overdue_sessions(db)
    csv_text = sessions_csv(db, teacher=user, scope_mode=settings.teacher_scope_mode)
    stamp = utc_now().strftime("%Y%m%d_%H%M")
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=zas_intellect_sessions_{stamp}.csv"},
    )
