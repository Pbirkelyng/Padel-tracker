from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth_utils import SESSION_COOKIE, load_session_token
from app.db import get_db
from app.models import User, UserStatus

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user_optional(
    db: DbSession,
    padel_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User | None:
    if not padel_session:
        return None
    user_id = load_session_token(padel_session)
    if user_id is None:
        return None
    return db.get(User, user_id)


def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_approved(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.status == UserStatus.pending:
        raise HTTPException(status_code=403, detail="Pending approval")
    if user.status == UserStatus.rejected:
        raise HTTPException(status_code=403, detail="Rejected")
    return user


def require_admin(user: Annotated[User, Depends(require_approved)]) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


ApprovedUser = Annotated[User, Depends(require_approved)]
AdminUser = Annotated[User, Depends(require_admin)]
