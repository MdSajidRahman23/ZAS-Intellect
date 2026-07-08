from functools import lru_cache
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ZAS-Intellect"
    app_version: str = "Adaptive Viva Ready"
    app_secret_key: str = "change-this-secret-before-demo"
    database_url: str = "sqlite:///./zas_intellect.db"
    upload_dir: str = "app/data/uploads"
    recording_dir: str = "app/data/recordings"
    max_upload_mb: int = 12
    min_readable_chars: int = 80
    viva_duration_minutes: int = 5
    min_answer_chars: int = 20

    # Adaptive viva controls. The next question becomes harder after a strong answer
    # and easier after a weak answer.
    enable_adaptive_viva: bool = True
    adaptive_question_count: int = 5
    adaptive_start_difficulty: int = 2
    adaptive_raise_threshold: int = 75
    adaptive_lower_threshold: int = 50

    # AI provider options: offline, gemini, grok, auto
    ai_provider: str = "auto"
    ai_timeout_seconds: int = 10
    ai_privacy_notice: bool = True

    # xAI/Grok settings. The project remains fully usable when no key is configured.
    xai_api_key: str = ""
    xai_base_url: str = "https://api.x.ai/v1"
    xai_model: str = "grok-4.3"

    # Optional Gemini backup.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    # UI / local demo settings.
    demo_mode: bool = True
    production_mode: bool = False
    show_demo_credentials: bool = True

    # Basic security controls for local/prototype deployment.
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 300

    # Optional STT provider. browser = client-side Web Speech API; openai = server Whisper endpoint.
    stt_provider: str = "browser"
    openai_api_key: str = ""
    openai_stt_model: str = "whisper-1"

    # Production/security controls.
    session_timeout_minutes: int = 45
    secure_cookies: bool = False
    teacher_scope_mode: str = "department"  # department / all
    enable_mediapipe_proctoring: bool = True
    enable_secure_fullscreen: bool = True
    secure_mode_end_on_fullscreen_exit: bool = True
    secure_mode_end_on_focus_loss: bool = True
    enable_video_recording: bool = True
    video_chunk_seconds: int = 10
    max_recording_chunk_mb: int = 18
    keep_recordings_for_all_sessions: bool = True
    motion_detection_enabled: bool = True
    motion_detection_interval_ms: int = 2500

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("ai_provider")
    @classmethod
    def validate_ai_provider(cls, value: str) -> str:
        value = (value or "auto").strip().lower()
        if value not in {"offline", "gemini", "grok", "auto"}:
            return "auto"
        return value

    @field_validator("viva_duration_minutes")
    @classmethod
    def validate_duration(cls, value: int) -> int:
        return max(3, min(int(value), 30))

    @field_validator("adaptive_question_count")
    @classmethod
    def validate_adaptive_question_count(cls, value: int) -> int:
        return max(3, min(int(value), 10))

    @field_validator("adaptive_start_difficulty")
    @classmethod
    def validate_adaptive_start_difficulty(cls, value: int) -> int:
        return max(1, min(int(value), 3))

    @field_validator("adaptive_raise_threshold", "adaptive_lower_threshold")
    @classmethod
    def validate_adaptive_threshold(cls, value: int) -> int:
        return max(0, min(int(value), 100))


    @field_validator("teacher_scope_mode")
    @classmethod
    def validate_teacher_scope_mode(cls, value: str) -> str:
        value = (value or "department").strip().lower()
        if value not in {"department", "all"}:
            return "department"
        return value

    @field_validator("stt_provider")
    @classmethod
    def validate_stt_provider(cls, value: str) -> str:
        value = (value or "browser").strip().lower()
        if value not in {"browser", "openai", "disabled"}:
            return "browser"
        return value

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def recording_path(self) -> Path:
        path = Path(self.recording_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def max_recording_chunk_bytes(self) -> int:
        return self.max_recording_chunk_mb * 1024 * 1024

    def validate_runtime(self) -> None:
        if (self.production_mode or not self.demo_mode) and self.app_secret_key == "change-this-secret-before-demo":
            raise RuntimeError("APP_SECRET_KEY must be changed when DEMO_MODE=false or PRODUCTION_MODE=true.")
        if self.production_mode and self.show_demo_credentials:
            raise RuntimeError("SHOW_DEMO_CREDENTIALS must be false when PRODUCTION_MODE=true.")
        if self.production_mode and not self.secure_cookies:
            raise RuntimeError("SECURE_COOKIES must be true when PRODUCTION_MODE=true.")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
