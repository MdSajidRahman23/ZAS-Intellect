from __future__ import annotations

import json
from sqlalchemy.orm import Session

from app.core.time_utils import utc_now
from app.core.config import get_settings
from app.models.database import ProctorEvent, VivaSession
from app.services.scoring import build_score_breakdown, proctor_risk_score


def question_stats(session: VivaSession) -> tuple[int, int]:
    target = get_settings().adaptive_question_count if get_settings().enable_adaptive_viva else len(session.questions)
    total = max(target, len(session.questions))
    answered = len([q for q in session.questions if (q.answer or "").strip()])
    return total, answered


def active_question(session: VivaSession):
    for q in sorted(session.questions, key=lambda item: item.q_order):
        if not (q.answer or "").strip():
            return q
    return None


def secure_has_started(session: VivaSession) -> bool:
    return bool(getattr(session, "secure_started_at", None))


def mark_secure_started(session: VivaSession) -> bool:
    """Start the official viva timer exactly once.

    Assignment upload creates a pending viva session, but the official 3-5 minute
    viva clock must not begin until camera, microphone, recording and fullscreen
    checks have all passed on the client.
    """
    if secure_has_started(session):
        return False
    now = utc_now()
    session.secure_started_at = now
    session.started_at = now
    return True


def remaining_seconds(session: VivaSession) -> int:
    if not secure_has_started(session):
        return max(0, int(session.viva_duration_seconds or 0))
    elapsed = (utc_now() - session.secure_started_at).total_seconds()
    return max(0, int((session.viva_duration_seconds or 0) - elapsed))


def is_expired(session: VivaSession) -> bool:
    return session.status == "in_progress" and secure_has_started(session) and remaining_seconds(session) <= 0


def finalize_session(db: Session, session: VivaSession, reason: str, allow_unanswered: bool = False) -> bool:
    """Finalize a viva session and calculate the official ZAS score.

    Manual finish requires every answer. Timer expiry / secure violation can
    finalize unanswered questions with zero score so the dashboard never stays
    stuck in `in_progress`.
    """
    if session.status == "completed":
        return True

    total, answered = question_stats(session)
    if answered < total and not allow_unanswered:
        return False

    if allow_unanswered:
        for q in session.questions:
            if not (q.answer or "").strip():
                q.answer = ""
                q.raw_score = 0.0
                q.answer_score = 0.0
                q.feedback = "No answer was submitted before the viva ended."
                q.rubric_json = json.dumps({
                    "raw_score": 0,
                    "adjusted_score": 0,
                    "difficulty_level": getattr(q, "difficulty_level", 2),
                    "conceptual_match": 0,
                    "reasoning": 0,
                    "submission_specificity": 0,
                    "confidence": 0,
                    "generic_penalty": 0,
                })
                q.ai_provider_used = "system"

    scores = [q.answer_score for q in session.questions if (q.answer or "").strip() or allow_unanswered]
    target_total, _ = question_stats(session)
    if allow_unanswered and len(scores) < target_total:
        scores.extend([0.0] * (target_total - len(scores)))
    viva_performance = sum(scores) / max(1, len(scores))
    events = [{"risk_weight": event.risk_weight} for event in session.proctor_events]
    proctor = proctor_risk_score(events)
    breakdown = build_score_breakdown(viva_performance, session.submission_quality, proctor)
    session.viva_performance = breakdown.viva_performance
    session.submission_quality = breakdown.submission_quality
    session.proctor_risk = breakdown.proctor_risk
    session.zas_score = breakdown.zas_score
    session.risk_flag = breakdown.risk_flag
    session.feedback_summary = breakdown.summary
    session.status = "completed"
    session.completed_reason = reason
    session.ended_at = utc_now()
    return True


def expire_overdue_sessions(db: Session) -> int:
    """Finalize in-progress sessions whose *official* server-side timer expired.

    Pending sessions that have not passed secure-start checks are not expired,
    because the official viva timer has not begun yet.
    """
    sessions = db.query(VivaSession).filter(VivaSession.status == "in_progress").all()
    count = 0
    for session in sessions:
        if is_expired(session):
            finalize_session(db, session, reason="timed_out_background", allow_unanswered=True)
            db.add(ProctorEvent(
                session_id=session.id,
                event_type="timer_expired_server",
                details="Server-side timer expired and finalized the viva automatically.",
                risk_weight=0.0,
            ))
            count += 1
    if count:
        db.commit()
    return count
