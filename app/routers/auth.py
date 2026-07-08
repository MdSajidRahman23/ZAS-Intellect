from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import (
    csrf_token,
    audit_log,
    authenticate,
    check_login_rate_limit,
    clear_failed_login,
    record_failed_login,
    validate_csrf,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["csrf_token"] = csrf_token
settings = get_settings()
templates.env.globals["settings"] = settings


@router.get("/login")
def login_page(request: Request, expired: int | None = Query(None)):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    error = "Session expired. Please login again." if expired else None
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": error, "settings": settings})


@router.post("/login")
def login(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    validate_csrf(request, csrf_token)
    check_login_rate_limit(request, identifier)
    user = authenticate(db, identifier, password)
    if not user:
        record_failed_login(request, identifier)
        audit_log(db, request, None, "login_failed", f"identifier={identifier[:80]}")
        db.commit()
        return templates.TemplateResponse(request, "login.html", {"request": request, "error": "Invalid ID or password", "settings": settings}, status_code=401)
    clear_failed_login(request, identifier)
    request.session["user_id"] = user.id
    request.session["role"] = user.role
    audit_log(db, request, user.id, "login_success", f"role={user.role}")
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    actor_id = request.session.get("user_id")
    audit_log(db, request, int(actor_id) if actor_id else None, "logout", "user logged out")
    db.commit()
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/logout")
def logout_get():
    raise HTTPException(status_code=405, detail="Logout must be submitted securely from the Logout button.")
