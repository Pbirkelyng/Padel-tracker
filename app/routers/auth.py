from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_utils import SESSION_COOKIE, create_session_token, hash_password, verify_password
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user_optional
from app.models import User, UserStatus
from app.templating import templates

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    error: str | None = None,
    next: str | None = None,
    user: User | None = Depends(get_current_user_optional),
):
    next_url = next or request.query_params.get("next") or ""
    if user:
        if user.status == UserStatus.pending:
            return RedirectResponse("/pending", status_code=303)
        if user.status == UserStatus.approved:
            dest = next_url if next_url.startswith("/") else "/"
            return RedirectResponse(dest, status_code=303)
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {"error": error, "user": None, "next_url": next_url},
    )


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next_hidden: str = Form(""),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Invalid email or password", "user": None, "next_url": next_hidden},
            status_code=400,
        )
    if user.status == UserStatus.rejected:
        return RedirectResponse("/login?error=rejected", status_code=303)

    if user.status == UserStatus.pending:
        dest = "/pending"
    elif next_hidden.strip().startswith("/"):
        dest = next_hidden.strip()
    else:
        dest = "/"

    token = create_session_token(user.id)
    settings = get_settings()
    max_age = settings.session_max_age_days * 86400
    redirect = RedirectResponse(dest, status_code=303)
    redirect.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=max_age,
    )
    return redirect


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "auth/register.html", {"error": None, "user": None})


@router.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.lower().strip()
    display_name = display_name.strip()
    if len(password) < 6:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"error": "Password must be at least 6 characters", "user": None},
            status_code=400,
        )
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"error": "Email already registered", "user": None},
            status_code=400,
        )

    settings = get_settings()
    is_admin_email = email == settings.admin_email.lower().strip()
    # Anyone can sign up; gatekeeping happens per-league (join requests / invites).
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name or email.split("@")[0],
        status=UserStatus.approved,
        is_admin=is_admin_email,
    )
    db.add(user)
    db.commit()

    token = create_session_token(user.id)
    redirect = RedirectResponse("/", status_code=303)
    redirect.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=30 * 86400)
    return redirect


@router.get("/pending", response_class=HTMLResponse)
def pending_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.status == UserStatus.approved:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "auth/pending.html", {"user": user})


@router.post("/logout")
def logout():
    redirect = RedirectResponse("/login", status_code=303)
    redirect.delete_cookie(SESSION_COOKIE)
    return redirect
