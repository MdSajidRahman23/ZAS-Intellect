# ZAS-Intellect Final Python — Adaptive Viva Build

A competition-ready Python/FastAPI implementation of **ZAS-Intellect: a multimodal AI-driven viva and academic integrity system for DIU BLC**.

This edition adds adaptive viva difficulty, secure full-screen viva mode, mandatory camera + microphone + recording checks, server-side secure-start locking, automatic termination on secure-mode violation, webcam video recording, MediaPipe face/gaze checks, tuned motion risk, teacher playback evidence, and Grok/Gemini/offline AI fallback.

## Key Features

- Python-only FastAPI backend
- DIU BLC-inspired student and teacher UI
- Student assignment upload: PDF, DOCX, TXT, Markdown, and common code files
- Stream-time upload size protection
- Readable-text validation for scanned/image-only PDFs
- Server-enforced timed 3–5 minute viva flow, default 5 minutes
- Background expiry worker so abandoned timed-out vivas do not stay stuck
- Bangla, English, and mixed-language answer support
- Adaptive viva difficulty: a strong answer raises the next question level, while a weak answer moves the student toward a foundation-level follow-up
- Difficulty-aware marking: Foundation questions are capped lower, Standard questions use normal marks, and Advanced questions receive a small difficulty bonus
- Optional Grok/xAI, optional Gemini, and always-available offline AI fallback
- Minimum 5-question enforcement with offline fill if provider returns too few questions
- Prompt-injection hardening for untrusted student submission text
- Question categories: Concept, Workflow, Implementation Decision, Limitation/Improvement, Validation, Ownership Check
- Rubric-based answer evaluation
- ZAS-Score formula: `Viva Performance × 0.6 + Submission Quality × 0.4`
- Secure full-screen viva start gate with explicit consent
- ESC/full-screen exit, tab switch, or window focus loss can auto-end the viva as a critical violation
- Webcam + microphone video recording using the browser MediaRecorder API
- Teacher video evidence playback, saved in configurable chunks
- MediaPipe face/gaze checks when CDN is available
- Browser frame-difference motion detection; no dataset required
- Proctor logging: webcam, face missing, multiple faces, gaze away, excessive motion, tab switching, copy/paste, right-click, inactivity, timer expiration
- Security-violation score cap and teacher-visible integrity recommendation
- Browser voice input by default; optional server-side Whisper STT via `STT_PROVIDER=openai`
- CSRF-protected forms and JSON proctor requests
- POST-only state-changing actions
- Session timeout, login rate limiting, CSP/security headers, production-mode guard
- Audit log model and route-level logging
- Teacher dashboard filters/search/provider diagnostics
- Department-scoped teacher access by default
- Teacher decision panel: Accepted, Needs Physical Viva, Penalized, Recheck Required
- Group project fairness comparison by group code
- CSV export with Excel formula-injection protection
- Unicode/Bangla-aware PDF report export using available OS fonts
- SQLite demo database with PostgreSQL-ready SQLAlchemy models
- Real Alembic initial migration script
- Isolated pytest database and workflow tests

## Windows Setup

Extract the ZIP to `D:\ZAS-Intellect`, then open PowerShell:

```powershell
cd "D:\ZAS-Intellect\zas_intellect_final_python"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup_windows.ps1
.\scripts\start_windows.ps1
```

Open:

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

The browser cannot be physically forced to stay in full-screen mode. The correct web-safe approach is implemented here: ZAS-Intellect requires the student to start full-screen mode and then detects ESC/full-screen exit, tab hiding, and focus loss. When a configured secure-mode violation happens, the viva is finalized immediately, proctor risk becomes critical, and the result is flagged as **Security Violation**.

Video recording is stored in `app/data/recordings/session_<id>/` as WebM chunks. For demo, recordings are kept for all sessions. For production, configure retention and storage policy according to institutional rules.

Motion detection does **not** need a downloaded dataset. This version uses MediaPipe for face/gaze signals and browser frame-difference logic for movement signals. A custom cheating-classifier dataset can be a future research extension, not an MVP requirement.

## Grok / xAI Setup

The project is safe without an API key. It uses the offline engine automatically. To enable Grok:

1. Copy `.env.example` to `.env` if setup did not do it already.
2. Set:

```env
AI_PROVIDER=auto
XAI_API_KEY=your_xai_api_key_here
XAI_MODEL=grok-4.3
```

`AI_PROVIDER=auto` tries:

```text
Grok → Gemini → Offline fallback
```

This demo-ready ZIP uses `AI_PROVIDER=auto` by default for stable local recording. Change it to `auto` only when API keys are available.

## Optional Server-Side Whisper STT

Browser voice input works without a backend key. For server-side STT:

```env
STT_PROVIDER=openai
OPENAI_API_KEY=your_openai_key_here
OPENAI_STT_MODEL=whisper-1
```

## Important Privacy Note

When Grok, Gemini, or server-side STT is enabled, extracted submission text or audio can be sent to the configured provider. Keep `AI_PROVIDER=auto` and `STT_PROVIDER=browser` for a fully local/no-external-API demo.

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
templates/    BLC-style HTML templates
static/       CSS and viva JS
scripts/      Windows setup/start/reset scripts
tests/        unit and workflow tests
alembic/      production migration scripts
```

## Notes for DIU BLC Visual Matching

This build is DIU/BLC-inspired. For pixel-perfect matching, replace header/sidebar colors, logos, and spacing after comparing with real DIU BLC screenshots.

## v6.1 Secure Proctoring Fix

This build fixes two browser-side issues found during manual testing:

- Camera/microphone prompt is now forced through a clearer secure-start flow. If the first click is consumed by the permission prompt, the interface asks for one more click to enter full-screen.
- Full-screen exit auto-end is now more reliable using standard + vendor fullscreen events, ESC detection, page-hide detection, and a fullscreen heartbeat check.
- Final video chunks are flushed before redirecting after a security violation, so teacher playback is more likely to include the last seconds before termination.

Use Chrome or Microsoft Edge and open the app from `http://127.0.0.1:8000` or `http://localhost:8000`. Camera/microphone prompts may not appear on plain LAN/IP URLs or when the browser has already blocked permission for the site.


## v6.2 Secure Start Lock Fix

This build fixes the manual-testing issues reported after v6.1:

- The official viva timer no longer starts at upload/page-load. It starts only after secure start is confirmed.
- The question area is visually locked before secure start, so students cannot read the question before camera/mic/full-screen checks pass.
- Server routes now block answer submission and manual finish until secure start has been confirmed.
- Camera and microphone are both mandatory. The previous webcam-only fallback was removed.
- Video recording must start successfully when video recording is enabled.
- The secure-start API records the official server timer start and supports resume without resetting the timer.
- Tests now verify timer lock, question lock, missing-microphone rejection, and answer blocking before secure start.


## v6.3.2 Live Camera Preview

This demo-ready build adds small reviewer-visible polish requested for the AI Project Competition progress update:

- Assignment page wording now matches the implemented secure-start flow.
- The submit button now says **Submit and Open Secure Viva** to avoid implying the timer starts before secure checks.
- Viva rules now clearly state that camera, microphone, recording, and full-screen mode are mandatory before the official timer starts.
- Teacher dashboard now includes a **Current Progress Since Initial Proposal** panel showing implemented features and enhancements since the proposal.
- Viva answers are now submitted through AJAX inside the same secure page. Camera, microphone, recording, and full-screen stay active across all five questions, so the browser should not ask for media permission again after every answer.
- `.env` is set to `AI_PROVIDER=auto` and `STT_PROVIDER=browser` for stable local demo recording without external API errors.

For the demo video, show the new teacher dashboard progress panel after completing one student viva session.


## Adaptive Viva Logic

The viva no longer treats all questions as the same difficulty. The first question starts at Standard level. After each answer, the system checks the raw evaluation score:

```text
Raw score >= 75  -> next question becomes harder, up to Advanced
Raw score 50-74  -> next question stays at the same level
Raw score < 50   -> next question becomes easier, down to Foundation
```

Official marking is also difficulty-aware:

```text
Foundation: easier question, official score capped at 75
Standard: normal question, official score capped at 90
Advanced: harder question, small bonus, official score capped at 100
```

Teacher and student reports show both the raw examiner score and the official difficulty-adjusted score.
