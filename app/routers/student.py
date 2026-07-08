import json
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import audit_log, csrf_token, require_role, validate_csrf
from app.models.database import Submission, User, VivaQuestion, VivaSession
from app.services.ai_engine import ai_engine
from app.services.file_parser import parse_submission
from app.services.reporting import session_pdf
from app.services.adaptive import adjusted_answer_score, difficulty_label, difficulty_note, next_difficulty_level
from app.services.session_manager import active_question, expire_overdue_sessions, finalize_session, is_expired, question_stats, remaining_seconds, secure_has_started
from app.core.time_utils import utc_now

router = APIRouter(prefix="/student")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["csrf_token"] = csrf_token
settings = get_settings()
templates.env.globals["settings"] = settings


def _wants_json(request: Request) -> bool:
    """Return True for AJAX viva submissions.

    The secure viva page keeps camera, microphone, recording and full-screen
    active while answers are submitted. Returning JSON prevents a full page
    reload between questions, so the browser does not ask for media permission
    again on every question.
    """
    return request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", "")


def _question_payload(question: VivaQuestion | None):
    if not question:
        return None
    return {
        "id": question.id,
        "category": question.category,
        "question": question.question,
        "provider": (question.ai_provider_used or "offline").upper(),
        "difficulty_level": getattr(question, "difficulty_level", 2) or 2,
        "difficulty_label": difficulty_label(getattr(question, "difficulty_level", 2)),
        "adaptive_note": getattr(question, "adaptive_note", "") or difficulty_note(getattr(question, "difficulty_level", 2)),
    }


def _answer_error(request: Request, session_id: int, error_code: str, message: str, status_code: int = 400):
    if _wants_json(request):
        return JSONResponse({"ok": False, "error": error_code, "message": message}, status_code=status_code)
    return RedirectResponse(f"/student/viva/{session_id}?error={error_code}", status_code=303)


def _assignment_context(request: Request, user: User, error: str | None = None):
    return {"request": request, "user": user, "error": error, "settings": settings, "ai_status": ai_engine.provider_status()}


def _existing_question_texts(session: VivaSession) -> list[str]:
    return [q.question for q in sorted(session.questions, key=lambda item: item.q_order)]


def _existing_raw_scores(session: VivaSession) -> list[float]:
    return [float(q.raw_score or q.answer_score or 0) for q in sorted(session.questions, key=lambda item: item.q_order) if (q.answer or "").strip()]




def _local_fallback_question(session: VivaSession, q_order: int, difficulty_level: int) -> VivaQuestion:
    """Create a safe built-in adaptive question if any AI/provider path fails.

    This keeps the student submission flow demo-safe even when an external
    provider, API key, network, or older local database state causes an error.
    """
    level = max(1, min(3, int(difficulty_level or 2)))
    question_bank = {
        1: [
            ("Concept", "Explain the main problem your submission is solving in simple words.", "problem, target user, why it matters, simple solution idea"),
            ("Workflow", "List the basic steps from assignment upload to teacher review.", "upload, read file, ask viva, check answer, show teacher result"),
            ("Validation", "How can a teacher check whether the generated result is fair?", "teacher review, transcript, score, evidence, follow-up viva"),
        ],
        2: [
            ("Concept", "Explain the core problem your submission is solving and why student understanding is important.", "AI/copying problem, ownership, understanding verification, teacher workload"),
            ("Workflow", "Walk through the full workflow step by step from file submission to ZAS-Score.", "submission, parsing, question generation, secure viva, evaluation, scoring, dashboard"),
            ("Implementation Decision", "Which technical decision is most important in your system, and what would fail without it?", "secure start, scoring formula, proctoring, database, fallback AI"),
        ],
        3: [
            ("Implementation Decision", "Defend one key architecture decision and explain its trade-off in a real DIU deployment.", "trade-off, reliability, privacy, scalability, teacher workflow"),
            ("Validation", "Design a validation plan to compare ZAS-Score with teacher judgement and reduce false flags.", "test cases, teacher rubric, metrics, false positives, review process"),
            ("Limitation/Improvement", "Identify one limitation of your prototype and propose a production-ready improvement.", "limitation, improvement, deployment, privacy, monitoring, accuracy"),
        ],
    }
    choices = question_bank[level]
    category, question, expected = choices[(q_order - 1) % len(choices)]
    return VivaQuestion(
        session=session,
        session_id=session.id,
        q_order=q_order,
        category=category,
        question=question,
        expected_points=expected,
        ai_provider_used="offline",
        difficulty_level=level,
        adaptive_note=difficulty_note(level),
    )

def _create_adaptive_question(db: Session, session: VivaSession, q_order: int, difficulty_level: int) -> VivaQuestion:
    try:
        draft = ai_engine.generate_adaptive_question(
            session.submission.extracted_text,
            q_order=q_order,
            difficulty_level=difficulty_level,
            previous_questions=_existing_question_texts(session),
            previous_scores=_existing_raw_scores(session),
        )
        row = VivaQuestion(
            session=session,
            session_id=session.id,
            q_order=q_order,
            category=draft.category,
            question=draft.question,
            expected_points=draft.expected_points,
            ai_provider_used=draft.provider,
            difficulty_level=draft.difficulty_level,
            adaptive_note=draft.adaptive_note or difficulty_note(draft.difficulty_level),
        )
        db.add(row)
        db.flush()
        if draft.provider != "offline":
            session.ai_provider_used = draft.provider
        return row
    except Exception:
        # Last-resort built-in fallback. Do not break the submission flow.
        row = _local_fallback_question(session, q_order, difficulty_level)
        db.add(row)
        db.flush()
        session.ai_provider_used = "offline"
        return row


async def _save_upload_stream(file: UploadFile, destination: Path, max_bytes: int) -> int:
    total = 0
    with destination.open("wb") as buffer:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                destination.unlink(missing_ok=True)
                raise ValueError(f"File too large. Max {settings.max_upload_mb} MB.")
            buffer.write(chunk)
    return total


@router.get("")
def dashboard(
    request: Request,
    msg: str | None = Query(None),
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    expire_overdue_sessions(db)
    sessions = db.query(VivaSession).filter(VivaSession.student_id == user.id).order_by(VivaSession.started_at.desc()).limit(10).all()
    return templates.TemplateResponse(request, "student_dashboard.html", {"request": request, "user": user, "sessions": sessions, "msg": msg})


@router.get("/assignment")
def assignment_page(request: Request, user: User = Depends(require_role("student"))):
    return templates.TemplateResponse(request, "assignment.html", _assignment_context(request, user))


@router.post("/submit")
async def submit_assignment(
    request: Request,
    assignment_title: str = Form("AI Project Competition Proposal"),
    course_code: str = Form("CSE-AI-2026"),
    group_code: str = Form(""),
    is_group_submission: str | None = Form(None),
    consent_ai_processing: str | None = Form(None),
    csrf_token: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    validate_csrf(request, csrf_token)
    if settings.ai_privacy_notice and not consent_ai_processing:
        return templates.TemplateResponse(request, "assignment.html", _assignment_context(request, user, "Please accept the AI processing notice before starting the viva."), status_code=400)
    if not file.filename:
        return templates.TemplateResponse(request, "assignment.html", _assignment_context(request, user, "Please choose a submission file."), status_code=400)

    suffix = Path(file.filename).suffix.lower()
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    stored_path = settings.upload_path / safe_name

    try:
        actual_size = await _save_upload_stream(file, stored_path, settings.max_upload_bytes)
    except ValueError as exc:
        return templates.TemplateResponse(request, "assignment.html", _assignment_context(request, user, str(exc)), status_code=413)

    if actual_size == 0:
        stored_path.unlink(missing_ok=True)
        return templates.TemplateResponse(request, "assignment.html", _assignment_context(request, user, "Uploaded file is empty."), status_code=400)

    try:
        extracted_text, file_type, word_count = parse_submission(stored_path)
    except Exception as exc:
        stored_path.unlink(missing_ok=True)
        return templates.TemplateResponse(request, "assignment.html", _assignment_context(request, user, str(exc)), status_code=400)

    readable_chars = len(extracted_text.strip())
    if readable_chars < settings.min_readable_chars or word_count < 12:
        stored_path.unlink(missing_ok=True)
        return templates.TemplateResponse(
            request,
            "assignment.html",
            _assignment_context(
                request,
                user,
                "This file has no readable text for viva generation. If it is a scanned PDF or image-only file, export it with selectable text or upload DOCX/TXT/code.",
            ),
            status_code=400,
        )

    quality = ai_engine.evaluate_submission_quality(extracted_text, word_count)
    submission = Submission(
        student_id=user.id,
        course_code=course_code.strip()[:50] or "CSE-AI-2026",
        assignment_title=assignment_title.strip()[:200] or "AI Project Competition Proposal",
        group_code=group_code.strip()[:80],
        is_group_submission=bool(is_group_submission or group_code.strip()),
        original_filename=file.filename[:255],
        stored_path=str(stored_path),
        file_type=file_type,
        extracted_text=extracted_text,
        word_count=word_count,
        submission_quality=quality,
    )
    db.add(submission)
    db.flush()

    viva = VivaSession(
        submission_id=submission.id,
        student_id=user.id,
        submission_quality=quality,
        status="in_progress",
        risk_flag="Pending",
        viva_duration_seconds=settings.viva_duration_minutes * 60,
    )
    db.add(viva)
    db.flush()

    if settings.enable_adaptive_viva:
        first_question = _create_adaptive_question(db, viva, q_order=1, difficulty_level=settings.adaptive_start_difficulty)
        provider_used = first_question.ai_provider_used or "offline"
    else:
        providers = []
        for index, draft in enumerate(ai_engine.generate_questions(extracted_text, count=settings.adaptive_question_count), start=1):
            providers.append(draft.provider)
            db.add(VivaQuestion(
                session_id=viva.id,
                q_order=index,
                category=draft.category,
                question=draft.question,
                expected_points=draft.expected_points,
                ai_provider_used=draft.provider,
                difficulty_level=getattr(draft, "difficulty_level", 2),
                adaptive_note=getattr(draft, "adaptive_note", "") or difficulty_note(getattr(draft, "difficulty_level", 2)),
            ))
        provider_used = providers[0] if providers else "offline"
    submission.ai_provider_used = provider_used
    viva.ai_provider_used = provider_used
    audit_log(db, request, user.id, "submission_uploaded", f"submission_id={submission.id}; viva_id={viva.id}; provider={provider_used}")
    db.commit()
    return RedirectResponse(f"/student/viva/{viva.id}", status_code=303)


@router.get("/viva/{session_id}")
def viva_page(
    request: Request,
    session_id: int,
    error: str | None = Query(None),
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    session = db.get(VivaSession, session_id)
    if not session or session.student_id != user.id:
        raise HTTPException(404, "Viva session not found")
    if session.status == "completed":
        return RedirectResponse(f"/student/result/{session.id}", status_code=303)
    if is_expired(session):
        finalize_session(db, session, reason="timed_out", allow_unanswered=True)
        audit_log(db, request, user.id, "viva_timed_out", f"session_id={session.id}")
        db.commit()
        return RedirectResponse(f"/student/result/{session.id}", status_code=303)

    question = active_question(session)
    total, answered = question_stats(session)
    error_text = None
    if error == "answer_all":
        error_text = "Please answer every viva question before finishing."
    elif error == "too_short":
        error_text = "Your answer is too short. Please explain the logic, steps, and decision clearly."
    elif error == "locked":
        error_text = "That question is already locked. Continue with the active viva question."
    elif error == "secure_not_started":
        error_text = "Secure viva has not started yet. Camera, microphone, recording, and full-screen checks must pass before answering."
    return templates.TemplateResponse(
        request,
        "viva.html",
        {
            "request": request,
            "user": user,
            "session": session,
            "question": question,
            "total": total,
            "answered": answered,
            "error": error_text,
            "remaining_seconds": remaining_seconds(session),
            "secure_started": secure_has_started(session),
        },
    )


@router.post("/viva/{session_id}/answer")
def answer_question(
    request: Request,
    session_id: int,
    question_id: int = Form(...),
    answer: str = Form(...),
    csrf_token: str = Form(...),
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    validate_csrf(request, csrf_token)
    session = db.get(VivaSession, session_id)
    if not session or session.student_id != user.id or session.status != "in_progress":
        raise HTTPException(404, "Viva session not found")
    if is_expired(session):
        finalize_session(db, session, reason="timed_out", allow_unanswered=True)
        audit_log(db, request, user.id, "viva_timed_out", f"session_id={session.id}")
        db.commit()
        if _wants_json(request):
            return JSONResponse({"ok": True, "completed": True, "redirect_url": f"/student/result/{session.id}", "message": "Viva timer expired."})
        return RedirectResponse(f"/student/result/{session.id}", status_code=303)
    if not secure_has_started(session):
        audit_log(db, request, user.id, "answer_blocked_secure_not_started", f"session_id={session.id}")
        db.commit()
        return _answer_error(request, session.id, "secure_not_started", "Secure viva has not started yet. Camera, microphone, recording, and full-screen checks must pass before answering.", status_code=409)

    active = active_question(session)
    question = db.get(VivaQuestion, question_id)
    if not question or question.session_id != session.id or not active or question.id != active.id:
        return _answer_error(request, session.id, "locked", "That question is already locked. Continue with the active viva question.", status_code=409)
    if (question.answer or "").strip():
        return _answer_error(request, session.id, "locked", "That question is already locked. Continue with the active viva question.", status_code=409)

    answer = answer.strip()
    if len(answer) < settings.min_answer_chars:
        return _answer_error(request, session.id, "too_short", "Your answer is too short. Please explain the logic, steps, and decision clearly.", status_code=400)

    evaluation = ai_engine.evaluate_answer(question.question, question.expected_points, answer, session.submission.extracted_text)
    official_score = adjusted_answer_score(evaluation.score, question.difficulty_level)
    level_label = difficulty_label(question.difficulty_level)
    question.answer = answer
    question.raw_score = evaluation.score
    question.answer_score = official_score
    question.feedback = f"{evaluation.feedback} Adaptive marking: raw {evaluation.score:.1f}, {level_label} level official score {official_score:.1f}."
    rubric = dict(evaluation.rubric or {})
    rubric.update({
        "raw_score": evaluation.score,
        "official_score": official_score,
        "difficulty_level": question.difficulty_level,
        "difficulty_label": level_label,
        "difficulty_cap": {1: 75, 2: 90, 3: 100}.get(int(question.difficulty_level or 2), 90),
    })
    question.rubric_json = json.dumps(rubric, ensure_ascii=False)
    question.ai_provider_used = evaluation.provider
    question.answered_at = utc_now()
    if evaluation.provider != "offline":
        session.ai_provider_used = evaluation.provider
    audit_log(db, request, user.id, "viva_answer_submitted", f"session_id={session.id}; question_id={question.id}; score={evaluation.score}; provider={evaluation.provider}")

    next_question = active_question(session)
    total, answered = question_stats(session)
    if settings.enable_adaptive_viva and not next_question and answered < total:
        next_level = next_difficulty_level(
            evaluation.score,
            question.difficulty_level,
            raise_threshold=settings.adaptive_raise_threshold,
            lower_threshold=settings.adaptive_lower_threshold,
        )
        next_question = _create_adaptive_question(db, session, q_order=answered + 1, difficulty_level=next_level)
        total, answered = question_stats(session)
        audit_log(db, request, user.id, "adaptive_question_generated", f"session_id={session.id}; q_order={next_question.q_order}; difficulty={next_level}; previous_raw_score={evaluation.score}")

    if next_question:
        db.commit()
        if _wants_json(request):
            return JSONResponse({
                "ok": True,
                "completed": False,
                "answered": answered,
                "total": total,
                "remaining_seconds": remaining_seconds(session),
                "current_score": official_score,
                "current_raw_score": evaluation.score,
                "current_difficulty": level_label,
                "next_question": _question_payload(next_question),
                "adaptive_message": f"Previous answer raw score {evaluation.score:.1f}. Next question level: {difficulty_label(next_question.difficulty_level)}.",
            })
        return RedirectResponse(f"/student/viva/{session.id}", status_code=303)

    finalize_session(db, session, reason="all_questions_answered", allow_unanswered=False)
    audit_log(db, request, user.id, "viva_completed", f"session_id={session.id}; zas_score={session.zas_score}")
    db.commit()
    if _wants_json(request):
        return JSONResponse({
            "ok": True,
            "completed": True,
            "redirect_url": f"/student/result/{session.id}",
            "current_score": official_score,
            "current_raw_score": evaluation.score,
            "current_difficulty": level_label,
            "message": "All questions answered. Opening ZAS-Score report...",
        })
    return RedirectResponse(f"/student/result/{session.id}", status_code=303)


@router.post("/finish/{session_id}")
def finish_viva(
    request: Request,
    session_id: int,
    csrf_token: str = Form(...),
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    validate_csrf(request, csrf_token)
    session = db.get(VivaSession, session_id)
    if not session or session.student_id != user.id:
        raise HTTPException(404, "Viva session not found")
    if session.status == "completed":
        return RedirectResponse(f"/student/result/{session.id}", status_code=303)
    if not secure_has_started(session):
        audit_log(db, request, user.id, "finish_blocked_secure_not_started", f"session_id={session.id}")
        db.commit()
        return RedirectResponse(f"/student/viva/{session.id}?error=secure_not_started", status_code=303)
    allow_unanswered = is_expired(session)
    ok = finalize_session(db, session, reason="manual_finish" if not allow_unanswered else "timed_out", allow_unanswered=allow_unanswered)
    if not ok:
        return RedirectResponse(f"/student/viva/{session.id}?error=answer_all", status_code=303)
    audit_log(db, request, user.id, "viva_completed", f"session_id={session.id}; reason={session.completed_reason}; zas_score={session.zas_score}")
    db.commit()
    return RedirectResponse(f"/student/result/{session.id}", status_code=303)


@router.get("/finish/{session_id}")
def finish_get():
    raise HTTPException(status_code=405, detail="Viva finish must be submitted securely from the Finish button.")


@router.get("/result/{session_id}")
def result_page(request: Request, session_id: int, user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    session = db.get(VivaSession, session_id)
    if not session or session.student_id != user.id:
        raise HTTPException(404, "Result not found")
    if session.status != "completed" and is_expired(session):
        finalize_session(db, session, reason="timed_out_result_check", allow_unanswered=True)
        audit_log(db, request, user.id, "viva_timed_out", f"session_id={session.id}; source=result_page")
        db.commit()
    if session.status != "completed":
        return RedirectResponse(f"/student/viva/{session.id}?error=answer_all", status_code=303)
    return templates.TemplateResponse(request, "result.html", {"request": request, "user": user, "session": session})


@router.get("/result/{session_id}/report.pdf")
def result_pdf(request: Request, session_id: int, user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    session = db.get(VivaSession, session_id)
    if not session or session.student_id != user.id:
        raise HTTPException(404, "Result not found")
    if session.status != "completed" and is_expired(session):
        finalize_session(db, session, reason="timed_out_pdf_check", allow_unanswered=True)
        audit_log(db, request, user.id, "viva_timed_out", f"session_id={session.id}; source=result_pdf")
        db.commit()
    if session.status != "completed":
        raise HTTPException(409, "Result is not available until viva is completed")
    pdf = session_pdf(session, user)
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=zas_report_session_{session.id}.pdf"})
