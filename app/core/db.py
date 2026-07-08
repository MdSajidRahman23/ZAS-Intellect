from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_add_missing_columns() -> None:
    """Tiny local-demo migration layer.

    It keeps older demo databases usable after v5 adds professional fields.
    For production/PostgreSQL, use Alembic scripts included in the project.
    """
    if not settings.database_url.startswith("sqlite"):
        return

    additions = {
        "submissions": {
            "group_code": "VARCHAR(80) DEFAULT ''",
            "is_group_submission": "BOOLEAN DEFAULT 0",
            "ai_provider_used": "VARCHAR(30) DEFAULT 'offline'",
        },
        "viva_sessions": {
            "ai_provider_used": "VARCHAR(30) DEFAULT 'offline'",
            "viva_duration_seconds": "INTEGER DEFAULT 300",
            "secure_started_at": "DATETIME",
            "completed_reason": "VARCHAR(80) DEFAULT ''",
            "decision_status": "VARCHAR(50) DEFAULT 'Pending Teacher Review'",
            "decision_note": "TEXT DEFAULT ''",
            "decided_by": "INTEGER",
            "decided_at": "DATETIME",
        },
        "viva_questions": {
            "category": "VARCHAR(80) DEFAULT 'Concept'",
            "raw_score": "FLOAT DEFAULT 0",
            "difficulty_level": "INTEGER DEFAULT 2",
            "adaptive_note": "TEXT DEFAULT ''",
            "rubric_json": "TEXT DEFAULT '{}'",
            "ai_provider_used": "VARCHAR(30) DEFAULT 'offline'",
            "answered_at": "DATETIME",
        },
        "audit_logs": {
            "ip_address": "VARCHAR(80) DEFAULT ''",
            "user_agent": "VARCHAR(300) DEFAULT ''",
        },
        "video_chunks": {
            "duration_ms": "INTEGER DEFAULT 0",
        },
    }

    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        for table_name, columns in additions.items():
            if table_name not in tables:
                continue
            existing = {col["name"] for col in inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")


def init_db() -> None:
    from app.models.database import User, Submission, VivaSession, VivaQuestion, ProctorEvent, VideoChunk, AuditLog  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _sqlite_add_missing_columns()
