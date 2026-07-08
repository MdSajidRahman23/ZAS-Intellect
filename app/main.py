from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import get_settings
from app.core.db import SessionLocal, init_db
from app.core.security import csrf_token
from app.core.time_utils import utc_now
from app.routers import api, auth, student, teacher
from app.seed import seed
from app.services.session_manager import expire_overdue_sessions

settings = get_settings()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["csrf_token"] = csrf_token
templates.env.globals["settings"] = settings


async def _expiry_worker() -> None:
    while True:
        await asyncio.sleep(30)
        try:
            with SessionLocal() as db:
                expire_overdue_sessions(db)
        except Exception:
            # The request-time expiry path is still authoritative; this worker is best-effort.
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.demo_mode:
        seed()
    task = asyncio.create_task(_expiry_worker())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="ZAS-Intellect Final Python", version=settings.app_version, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret_key,
    same_site="strict" if settings.production_mode else "lax",
    https_only=settings.secure_cookies or settings.production_mode,
    max_age=settings.session_timeout_minutes * 60,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.middleware("http")
async def security_headers_and_session_timeout(request: Request, call_next):
    now = int(utc_now().timestamp())
    last_seen = request.session.get("last_seen_at") if "session" in request.scope else None
    if last_seen and now - int(last_seen) > settings.session_timeout_minutes * 60:
        request.session.clear()
        if request.url.path not in {"/", "/login", "/health"} and not request.url.path.startswith("/static/"):
            return RedirectResponse("/login?expired=1", status_code=303)
    if "session" in request.scope:
        request.session["last_seen_at"] = now

    response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), fullscreen=(self)")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'self';"
    )
    return response


app.include_router(auth.router)
app.include_router(student.router)
app.include_router(teacher.router)
app.include_router(api.router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if 300 <= exc.status_code < 400 and exc.headers and exc.headers.get("Location"):
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)
    role = request.session.get("role") if "session" in request.scope else None
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "user": None,
            "status_code": exc.status_code,
            "title": "Access issue" if exc.status_code == 403 else "Page not found" if exc.status_code == 404 else "Something went wrong",
            "message": exc.detail if isinstance(exc.detail, str) else "The request could not be completed.",
            "home_url": "/student" if role == "student" else "/teacher" if role == "teacher" else "/login",
        },
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "user": None,
            "status_code": 422,
            "title": "Invalid request",
            "message": "Some required information was missing or invalid. Please go back and try again.",
            "home_url": "/",
        },
        status_code=422,
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "user": None,
            "status_code": 500,
            "title": "Server error",
            "message": "ZAS-Intellect could not complete this action. Please restart the local server or try again.",
            "home_url": "/",
        },
        status_code=500,
    )


@app.get("/")
def home(request: Request):
    role = request.session.get("role")
    if role == "student":
        return RedirectResponse("/student", status_code=303)
    if role == "teacher":
        return RedirectResponse("/teacher", status_code=303)
    return RedirectResponse("/login", status_code=303)


@app.get("/health")
def health():
    with SessionLocal() as db:
        expired = expire_overdue_sessions(db)
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version, "demo_mode": settings.demo_mode, "expired_sessions_checked": expired}
