"""Initial ZAS-Intellect schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identifier", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("email", sa.String(150), nullable=False, server_default=""),
        sa.Column("role", sa.String(20), nullable=False, index=True),
        sa.Column("department", sa.String(80), nullable=False, server_default="CSE"),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_identifier", "users", ["identifier"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("course_code", sa.String(50), nullable=False, server_default="CSE-AI-2026"),
        sa.Column("assignment_title", sa.String(200), nullable=False, server_default="AI Project Competition Proposal"),
        sa.Column("group_code", sa.String(80), nullable=False, server_default=""),
        sa.Column("is_group_submission", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(30), nullable=False, server_default="unknown"),
        sa.Column("extracted_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submission_quality", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ai_provider_used", sa.String(30), nullable=False, server_default="offline"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_submissions_student_id", "submissions", ["student_id"])

    op.create_table(
        "viva_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("submission_id", sa.Integer(), sa.ForeignKey("submissions.id"), nullable=False, index=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="in_progress"),
        sa.Column("viva_performance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("submission_quality", sa.Float(), nullable=False, server_default="0"),
        sa.Column("proctor_risk", sa.Float(), nullable=False, server_default="0"),
        sa.Column("zas_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("risk_flag", sa.String(50), nullable=False, server_default="Pending"),
        sa.Column("feedback_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("ai_provider_used", sa.String(30), nullable=False, server_default="offline"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("secure_started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("viva_duration_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("completed_reason", sa.String(80), nullable=False, server_default=""),
        sa.Column("decision_status", sa.String(50), nullable=False, server_default="Pending Teacher Review"),
        sa.Column("decision_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_viva_sessions_submission_id", "viva_sessions", ["submission_id"])
    op.create_index("ix_viva_sessions_student_id", "viva_sessions", ["student_id"])

    op.create_table(
        "viva_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("viva_sessions.id"), nullable=False, index=True),
        sa.Column("q_order", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(80), nullable=False, server_default="Concept"),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_points", sa.Text(), nullable=False, server_default=""),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("answer_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("difficulty_level", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("adaptive_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("feedback", sa.Text(), nullable=False, server_default=""),
        sa.Column("rubric_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("ai_provider_used", sa.String(30), nullable=False, server_default="offline"),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_viva_questions_session_id", "viva_questions", ["session_id"])

    op.create_table(
        "proctor_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("viva_sessions.id"), nullable=False, index=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("details", sa.Text(), nullable=False, server_default=""),
        sa.Column("risk_weight", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_proctor_events_session_id", "proctor_events", ["session_id"])

    op.create_table(
        "video_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("viva_sessions.id"), nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stored_path", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False, server_default="video/webm"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_video_chunks_session_id", "video_chunks", ["session_id"])


    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("ip_address", sa.String(80), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(300), nullable=False, server_default=""),
        sa.Column("details", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_index("ix_video_chunks_session_id", table_name="video_chunks")
    op.drop_table("video_chunks")
    op.drop_index("ix_proctor_events_session_id", table_name="proctor_events")
    op.drop_table("proctor_events")
    op.drop_index("ix_viva_questions_session_id", table_name="viva_questions")
    op.drop_table("viva_questions")
    op.drop_index("ix_viva_sessions_student_id", table_name="viva_sessions")
    op.drop_index("ix_viva_sessions_submission_id", table_name="viva_sessions")
    op.drop_table("viva_sessions")
    op.drop_index("ix_submissions_student_id", table_name="submissions")
    op.drop_table("submissions")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_identifier", table_name="users")
    op.drop_table("users")
