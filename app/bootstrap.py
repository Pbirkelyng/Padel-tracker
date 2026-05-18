"""Database initialization and admin bootstrap."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, engine
from app.models import User, UserStatus


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def bootstrap_admin(db: Session) -> None:
    settings = get_settings()
    admin_email = settings.admin_email.lower().strip()
    if not admin_email:
        return

    user = db.scalar(select(User).where(User.email == admin_email))
    if user:
        if not user.is_admin or user.status != UserStatus.approved:
            user.is_admin = True
            user.status = UserStatus.approved
            db.commit()
    # Admin account is created on first register with that email, or manually

