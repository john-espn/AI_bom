from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import User


ROLE_LABELS = {"buyer": "采购人员", "engineer": "工艺/技术人员", "admin": "系统管理员"}


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username, User.is_active.is_(True)))
    if user and user.password == password:
        return user
    return None


def current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    return user if user and user.is_active else None


def require_user(request: Request, db: Session) -> User:
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


def require_role(user: User, *roles: str) -> None:
    if user.role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权执行此操作")
