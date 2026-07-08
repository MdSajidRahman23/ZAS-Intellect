from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import audit_log, current_user, validate_csrf_header
from app.models.database import ProctorEvent, VideoChunk, VivaSession, User
from app.services.proctoring import event_label, is_critical_event, risk_weight
from app.services.scoring import proctor_risk_score
from app.services.session_manager import finalize_session, is_expired, mark_secure_started, remaining_seconds, secure_has_started

router = APIRouter(prefix="/api")
settings = get_settings()


def _refresh_proctor_risk(db: Session, session: VivaSession) -> float:
    all_events = db.query(ProctorEvent).filter(ProctorEvent.session_id == session.id).all()
    session.proctor_risk = proctor_risk_score([{"risk_weight": item.risk_weight} for item in all_events])
    return session.proctor_risk


def _record_event(db: Session, session: VivaSession, event_type: str, details: str = "") -> ProctorEvent:
    event_type = str(event_type or "unknown")[:80]
    event = ProctorEvent(
        session_id=session.id,
        event_type=event_type,
        details=(details or event_label(event_type))[:1000],
        risk_weight=risk_weight(event_type),
    )
    db.add(event)
    db.flush()
    _refresh_proctor_risk(db, session)
    return event


@router.post("/proctor/{session_id}")
async def proctor_event(session_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    validate_csrf_header(request)
    session = db.get(VivaSession, session_id)
    if not session or session.student_id != user.id:
        raise HTTPException(404, "Session not found")
    if session.status != "in_progress":
        raise HTTPException(409, "Proctor logging is closed for completed sessions")
    if is_expired(session):
        finalize_session(db, session, reason="timed_out_proctor_check", allow_unanswered=True)
        audit_log(db, request, user.id, "viva_timed_out", f"session_id={session.id}; source=proctor_api")
        db.commit()
        raise HTTPException(409, "Viva timer has expired; session was finalized")

    payload = await request.json()
    event_type = str(payload.get("event_type", "unknown"))[:80]
    details = str(payload.get("details", event_label(event_type)))[:1000]
    event = _record_event(db, session, event_type, details)
    audit_log(db, request, user.id, "proctor_event", f"session_id={session.id}; event={event.event_type}; risk={event.risk_weight}")
    db.commit()
    return {"ok": True, "risk_weight": event.risk_weight, "session_proctor_risk": session.proctor_risk}



@router.post("/secure-start/{session_id}")
async def secure_start(session_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Confirm that mandatory secure-proctoring prerequisites passed, then start the official timer.

    The browser can ask for camera/microphone/fullscreen permissions only after a
    user click. The server records the official timer start only after the client
    confirms: live camera, live microphone, fullscreen active, and recording active.
    Without this confirmation, answer/finish routes remain locked.
    """
    validate_csrf_header(request)
    session = db.get(VivaSession, session_id)
    if not session or session.student_id != user.id:
        raise HTTPException(404, "Session not found")
    if session.status != "in_progress":
        return {"ok": True, "redirect_url": f"/student/result/{session.id}", "status": "already_completed"}

    payload = await request.json()
    camera_ok = bool(payload.get("camera_ok"))
    microphone_ok = bool(payload.get("microphone_ok"))
    fullscreen_ok = bool(payload.get("fullscreen_ok")) or not settings.enable_secure_fullscreen
    recording_ok = bool(payload.get("recording_ok")) or not settings.enable_video_recording

    missing = []
    if not camera_ok:
        missing.append("camera")
    if not microphone_ok:
        missing.append("microphone")
    if settings.enable_secure_fullscreen and not fullscreen_ok:
        missing.append("full-screen")
    if settings.enable_video_recording and not recording_ok:
        missing.append("video recording")

    if missing:
        details = "Secure viva start blocked. Missing required prerequisite(s): " + ", ".join(missing)
        _record_event(db, session, "secure_start_blocked", details)
        audit_log(db, request, user.id, "secure_start_blocked", f"session_id={session.id}; missing={','.join(missing)}")
        db.commit()
        raise HTTPException(409, details)

    first_start = mark_secure_started(session)
    if first_start:
        _record_event(db, session, "secure_mode_started", "Mandatory camera, microphone, recording, and full-screen checks passed. Official viva timer started.")
        action = "secure_viva_started"
    else:
        _record_event(db, session, "secure_mode_resumed", "Student reconnected secure camera/microphone/full-screen controls for the active viva.")
        action = "secure_viva_resumed"

    audit_log(db, request, user.id, action, f"session_id={session.id}; remaining={remaining_seconds(session)}")
    db.commit()
    return {"ok": True, "status": "started" if first_start else "resumed", "remaining_seconds": remaining_seconds(session)}

@router.post("/secure-terminate/{session_id}")
async def secure_terminate(session_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Terminate a viva when secure full-screen mode is violated.

    Browsers cannot be forced to remain in full-screen, so the professional pattern is:
    detect exit/focus-loss, record an evidence event, finalize the viva, and cap the score
    through the proctor-risk scoring rules.
    """
    validate_csrf_header(request)
    session = db.get(VivaSession, session_id)
    if not session or session.student_id != user.id:
        raise HTTPException(404, "Session not found")
    if session.status == "completed":
        return {"ok": True, "redirect_url": f"/student/result/{session.id}", "status": "already_completed"}

    payload = await request.json()
    event_type = str(payload.get("event_type", "secure_mode_terminated"))[:80]
    details = str(payload.get("details", "Secure viva mode was violated; session ended automatically."))[:1000]
    _record_event(db, session, event_type, details)
    if not is_critical_event(event_type):
        _record_event(db, session, "secure_mode_terminated", "Secure mode terminated the viva automatically after a protected-mode violation.")
    finalize_session(db, session, reason=event_type, allow_unanswered=True)
    audit_log(db, request, user.id, "secure_viva_terminated", f"session_id={session.id}; reason={event_type}; proctor_risk={session.proctor_risk}")
    db.commit()
    return {"ok": True, "redirect_url": f"/student/result/{session.id}", "status": "terminated"}


async def _openai_whisper_transcribe(audio: UploadFile) -> str:
    if not settings.openai_api_key:
        raise HTTPException(503, "OPENAI_API_KEY is missing, so server-side Whisper STT cannot run.")
    suffix = Path(audio.filename or "answer.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        while True:
            chunk = await audio.read(1024 * 1024)
            if not chunk:
                break
            tmp.write(chunk)
        tmp_path = Path(tmp.name)
    try:
        with tmp_path.open("rb") as fh:
            files = {"file": (audio.filename or "answer.webm", fh, audio.content_type or "audio/webm")}
            data = {"model": settings.openai_stt_model, "language": "bn"}
            async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds + 15) as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    data=data,
                    files=files,
                )
        if response.status_code >= 400:
            raise HTTPException(response.status_code, f"STT provider error: {response.text[:300]}")
        payload = response.json()
        text = str(payload.get("text", "")).strip()
        if not text:
            raise HTTPException(422, "The STT provider returned no transcript.")
        return text
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/stt/{session_id}")
async def speech_to_text(session_id: int, request: Request, audio: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    validate_csrf_header(request)
    session = db.get(VivaSession, session_id)
    if not session or session.student_id != user.id or session.status != "in_progress":
        raise HTTPException(404, "Session not found")
    if is_expired(session):
        finalize_session(db, session, reason="timed_out_stt_check", allow_unanswered=True)
        audit_log(db, request, user.id, "viva_timed_out", f"session_id={session.id}; source=stt_api")
        db.commit()
        raise HTTPException(409, "Viva timer has expired; session was finalized")
    if settings.stt_provider == "disabled":
        raise HTTPException(501, "Server-side STT is disabled in this build.")
    if settings.stt_provider == "browser":
        raise HTTPException(501, "Server-side STT is not configured. Use browser voice input or set STT_PROVIDER=openai.")
    if settings.stt_provider == "openai":
        transcript = await _openai_whisper_transcribe(audio)
        audit_log(db, request, user.id, "server_stt_completed", f"session_id={session.id}; chars={len(transcript)}")
        db.commit()
        return {"ok": True, "text": transcript}
    raise HTTPException(501, "Configured STT provider is not implemented.")


@router.post("/recording/{session_id}")
async def upload_recording_chunk(
    session_id: int,
    request: Request,
    chunk_index: int = Form(0),
    duration_ms: int = Form(0),
    video: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    validate_csrf_header(request)
    if not settings.enable_video_recording:
        raise HTTPException(409, "Video recording is disabled by configuration.")
    session = db.get(VivaSession, session_id)
    if not session or session.student_id != user.id:
        raise HTTPException(404, "Session not found")
    if session.status == "in_progress" and not secure_has_started(session):
        raise HTTPException(409, "Video evidence upload is locked until secure viva start is confirmed.")

    safe_index = max(0, min(int(chunk_index or 0), 10000))
    folder = settings.recording_path / f"session_{session.id}"
    folder.mkdir(parents=True, exist_ok=True)
    suffix = ".webm"
    target = folder / f"chunk_{safe_index:05d}{suffix}"
    total = 0
    with target.open("wb") as buffer:
        while True:
            data = await video.read(1024 * 1024)
            if not data:
                break
            total += len(data)
            if total > settings.max_recording_chunk_bytes:
                target.unlink(missing_ok=True)
                _record_event(db, session, "recording_failed", f"Recording chunk {safe_index} exceeded configured size limit.")
                db.commit()
                raise HTTPException(413, "Recording chunk is too large.")
            buffer.write(data)

    row = VideoChunk(
        session_id=session.id,
        chunk_index=safe_index,
        stored_path=str(target),
        mime_type=(video.content_type or "video/webm")[:80],
        size_bytes=total,
        duration_ms=max(0, min(int(duration_ms or 0), 600000)),
    )
    db.add(row)
    if session.status == "in_progress":
        _record_event(db, session, "recording_chunk_saved", f"Saved video evidence chunk #{safe_index} ({total} bytes).")
    audit_log(db, request, user.id, "recording_chunk_uploaded", f"session_id={session.id}; chunk={safe_index}; bytes={total}")
    db.commit()
    return {"ok": True, "chunk_id": row.id, "bytes": total}
