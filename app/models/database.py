from datetime import datetime
from app.core.time_utils import utc_now
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    identifier: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(150), default="")
    role: Mapped[str] = mapped_column(String(20), index=True)  # student / teacher
    department: Mapped[str] = mapped_column(String(80), default="CSE")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    submissions: Mapped[list["Submission"]] = relationship(back_populates="student")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    course_code: Mapped[str] = mapped_column(String(50), default="CSE-AI-2026")
    assignment_title: Mapped[str] = mapped_column(String(200), default="AI Project Competition Proposal")
    group_code: Mapped[str] = mapped_column(String(80), default="")
    is_group_submission: Mapped[bool] = mapped_column(Boolean, default=False)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(30), default="unknown")
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    submission_quality: Mapped[float] = mapped_column(Float, default=0.0)
    ai_provider_used: Mapped[str] = mapped_column(String(30), default="offline")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    student: Mapped[User] = relationship(back_populates="submissions")
    viva_sessions: Mapped[list["VivaSession"]] = relationship(back_populates="submission")


class VivaSession(Base):
    __tablename__ = "viva_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="in_progress")
    viva_performance: Mapped[float] = mapped_column(Float, default=0.0)
    submission_quality: Mapped[float] = mapped_column(Float, default=0.0)
    proctor_risk: Mapped[float] = mapped_column(Float, default=0.0)
    zas_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_flag: Mapped[str] = mapped_column(String(50), default="Pending")
    feedback_summary: Mapped[str] = mapped_column(Text, default="")
    ai_provider_used: Mapped[str] = mapped_column(String(30), default="offline")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    secure_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    viva_duration_seconds: Mapped[int] = mapped_column(Integer, default=300)
    completed_reason: Mapped[str] = mapped_column(String(80), default="")
    decision_status: Mapped[str] = mapped_column(String(50), default="Pending Teacher Review")
    decision_note: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    submission: Mapped[Submission] = relationship(back_populates="viva_sessions")
    questions: Mapped[list["VivaQuestion"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    proctor_events: Mapped[list["ProctorEvent"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    video_chunks: Mapped[list["VideoChunk"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class VivaQuestion(Base):
    __tablename__ = "viva_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("viva_sessions.id"), index=True)
    q_order: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(80), default="Concept")
    question: Mapped[str] = mapped_column(Text)
    expected_points: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    raw_score: Mapped[float] = mapped_column(Float, default=0.0)
    answer_score: Mapped[float] = mapped_column(Float, default=0.0)
    difficulty_level: Mapped[int] = mapped_column(Integer, default=2)
    adaptive_note: Mapped[str] = mapped_column(Text, default="")
    feedback: Mapped[str] = mapped_column(Text, default="")
    rubric_json: Mapped[str] = mapped_column(Text, default="{}")
    ai_provider_used: Mapped[str] = mapped_column(String(30), default="offline")
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def difficulty_label(self) -> str:
        labels = {1: "Foundation", 2: "Standard", 3: "Advanced"}
        try:
            level = int(self.difficulty_level or 2)
        except Exception:
            level = 2
        return labels.get(max(1, min(3, level)), "Standard")

    session: Mapped[VivaSession] = relationship(back_populates="questions")


class ProctorEvent(Base):
    __tablename__ = "proctor_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("viva_sessions.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    details: Mapped[str] = mapped_column(Text, default="")
    risk_weight: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    session: Mapped[VivaSession] = relationship(back_populates="proctor_events")


class VideoChunk(Base):
    __tablename__ = "video_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("viva_sessions.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    stored_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(80), default="video/webm")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    session: Mapped[VivaSession] = relationship(back_populates="video_chunks")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(120))
    ip_address: Mapped[str] = mapped_column(String(80), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
