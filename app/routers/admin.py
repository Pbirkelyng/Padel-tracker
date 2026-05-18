from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AdminUser
from app.models import User, UserStatus
from app.templating import templates

router = APIRouter(tags=["admin"], prefix="/admin")


@router.get("", response_class=HTMLResponse)
def admin_page(request: Request, user: AdminUser, db: Session = Depends(get_db)):
    pending = db.scalars(
        select(User)
        .where(User.status == UserStatus.pending, User.is_placeholder.is_(False))
        .order_by(User.created_at)
    ).all()
    approved = db.scalars(
        select(User)
        .where(User.status == UserStatus.approved, User.is_placeholder.is_(False))
        .order_by(User.display_name)
    ).all()
    return templates.TemplateResponse(
        request,
        "admin/index.html",
        {"user": user, "pending": pending, "approved": approved, "league_slug": ""},
    )


@router.post("/users/{user_id}/approve")
def approve_user(user_id: int, user: AdminUser, db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target:
        target.status = UserStatus.approved
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/users/{user_id}/reject")
def reject_user(user_id: int, user: AdminUser, db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target and target.id != user.id:
        target.status = UserStatus.rejected
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/users/{user_id}/promote")
def promote_admin(user_id: int, user: AdminUser, db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target:
        target.is_admin = True
        target.status = UserStatus.approved
        db.commit()
    return RedirectResponse("/admin", status_code=303)
