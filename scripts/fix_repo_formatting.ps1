# ZAS-Intellect final formatting fix
# Run from: D:\ZAS-Intellect

if (!(Test-Path "app\main.py")) {
    Write-Host "Run this from the ZAS-Intellect project root: D:\ZAS-Intellect" -ForegroundColor Red
    exit 1
}

@'
# ZAS-Intellect

A competition-ready Python/FastAPI implementation of **ZAS-Intellect**: a multimodal AI-driven viva and academic integrity system for academic assessment.

This build includes adaptive viva difficulty, secure full-screen viva mode, mandatory camera + microphone checks, webcam recording, teacher evidence playback, rubric-based evaluation, and optional AI provider support with an offline fallback.

## Key Features

- Python/FastAPI backend
- Student and teacher interfaces
- Student assignment upload: PDF, DOCX, TXT, Markdown, and common code files
- Readable-text validation for scanned or image-only PDFs
- Timed 3-5 minute viva flow, default 5 minutes
- Bangla, English, and mixed-language answer support
- Adaptive viva difficulty
- Difficulty-aware marking
- Optional Grok/xAI and Gemini support
- Offline AI fallback when no API key is available
- Minimum 5-question enforcement
- Prompt-injection hardening for untrusted student submission text
- Rubric-based answer evaluation
- Secure full-screen viva start gate with explicit consent
- Webcam + microphone video recording using the browser MediaRecorder API
- Teacher video evidence playback
- MediaPipe face/gaze checks when CDN access is available
- Browser frame-difference motion detection
- Proctor logging for webcam, face, gaze, motion, tab switch, copy/paste, right-click, inactivity, and timer events
- Browser voice input by default
- Optional server-side Whisper STT via `STT_PROVIDER=openai`
- CSRF-protected forms and JSON proctor requests
- POST-only state-changing actions
- Session timeout, login rate limiting, CSP/security headers, and production-mode guard
- Teacher dashboard filters/search/provider diagnostics
- Department-scoped teacher access by default
- Teacher decision panel
- Group project fairness comparison by group code
- CSV export with Excel formula-injection protection
- Unicode/Bangla-aware PDF report export using available OS fonts
- SQLite demo database
- PostgreSQL-ready SQLAlchemy models
- Alembic migration support
- Isolated pytest database and workflow tests

## ZAS Score

```text
Viva Performance x 0.6 + Submission Quality x 0.4
```

## Windows Setup

Keep the project directly in this folder:

```text
D:\ZAS-Intellect
```

Open PowerShell and run:

```powershell
cd "D:\ZAS-Intellect"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup_windows.ps1
.\scripts\start_windows.ps1
```

Open in browser:

```text
http://127.0.0.1:8000
```

## Demo Login

```text
Student: 0242220005101027 / student123
Student: 0242220005101473 / student123
Teacher: CIS-TEACHER / teacher123
```

## Secure Proctoring Notes

The browser cannot physically force a student to stay in full-screen mode. This project uses the web-safe approach: it asks the student to enter full-screen mode, then detects ESC/full-screen exit, tab hiding, and focus loss.

When a configured secure-mode violation occurs, the viva is finalized, proctor risk becomes critical, and the result is flagged as **Security Violation**.

Video recordings are stored in:

```text
app/data/recordings/session_<id>/
```

For demo use, recordings may be retained locally. For production use, configure a clear consent, retention, deletion, and storage policy according to institutional rules.

## Grok / xAI Setup

The project works without an API key by using the offline engine automatically.

To enable Grok/xAI, copy `.env.example` to `.env` and set:

```env
AI_PROVIDER=auto
XAI_API_KEY=your_xai_api_key_here
XAI_MODEL=grok-4.3
```

`AI_PROVIDER=auto` tries:

```text
Grok -> Gemini -> Offline fallback
```

## Optional Server-Side Whisper STT

Browser voice input works without a backend key.

For server-side STT:

```env
STT_PROVIDER=openai
OPENAI_API_KEY=your_openai_key_here
OPENAI_STT_MODEL=whisper-1
```

## Important Privacy Note

When Grok, Gemini, or server-side STT is enabled, extracted submission text or audio may be sent to the configured external provider.

For a fully local/no-external-API demo, keep:

```env
AI_PROVIDER=auto
STT_PROVIDER=browser
```

## Useful Commands

Reset demo database:

```powershell
.\scripts\reset_db.ps1
```

Run tests:

```powershell
.\.venv\Scripts\Activate.ps1
pytest -q
```

Start manually:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

Run Alembic migration in a real deployment:

```powershell
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

## Folder Structure

```text
app/
  core/       settings, DB, security, time helpers
  models/     SQLAlchemy models
  routers/    auth, student, teacher, API routes
  services/   AI engine, scoring, file parsing, reporting, proctoring, session manager
templates/    HTML templates
static/       CSS and viva JavaScript
scripts/      Windows setup/start/reset scripts
tests/        unit and workflow tests
alembic/      production migration scripts
```

## Production Checklist

Before real deployment:

```env
APP_SECRET_KEY=replace-with-a-strong-secret
DEMO_MODE=false
SHOW_DEMO_CREDENTIALS=false
SECURE_COOKIES=true
PRODUCTION_MODE=true
```

Also review:

- database credentials
- HTTPS setup
- storage path for recordings
- privacy/consent wording
- recording retention period
- external AI/STT provider usage
- access control for teachers/admins

## Adaptive Viva Logic

The first question starts at Standard level. After each answer, the system checks the raw evaluation score:

```text
Raw score >= 75 -> next question becomes harder, up to Advanced
Raw score 50-74 -> next question stays at the same level
Raw score < 50  -> next question becomes easier, down to Foundation
```

Official marking is difficulty-aware:

```text
Foundation: easier question, official score capped at 75
Standard: normal question, official score capped at 90
Advanced: harder question, small bonus, official score capped at 100
```

Teacher and student reports show both the raw examiner score and the official difficulty-adjusted score.
'@ | Set-Content "README.md" -Encoding UTF8

@'
.venv/
__pycache__/
*.pyc
.pytest_cache/

# Local environment
.env

# Local databases
*.db
*.sqlite
*.sqlite3

# App data
app/data/uploads/*
!app/data/uploads/.gitkeep
app/data/recordings/*
!app/data/recordings/.gitkeep

# Logs and OS files
*.log
.DS_Store
Thumbs.db
'@ | Set-Content ".gitignore" -Encoding UTF8

@'
fastapi==0.115.6
uvicorn[standard]==0.34.0
SQLAlchemy==2.0.36
Jinja2==3.1.4
python-multipart==0.0.20
itsdangerous==2.2.0
pydantic-settings==2.7.1
pypdf==5.1.0
python-docx==1.1.2
google-generativeai==0.8.3
httpx==0.28.1
reportlab==4.4.3
alembic==1.14.0
pytest==8.3.4
psycopg[binary]
'@ | Set-Content "requirements.txt" -Encoding UTF8

Write-Host "Formatted README.md, .gitignore, and requirements.txt." -ForegroundColor Green
Write-Host "Now run:" -ForegroundColor Cyan
Write-Host "git status"
Write-Host "git add README.md .gitignore requirements.txt"
Write-Host 'git commit -m "Fix repository file formatting"'
Write-Host "git push"
