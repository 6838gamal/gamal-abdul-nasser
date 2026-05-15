"""خدمات المصادقة والاعتماديات."""
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.models.user import User
from app.core.security import decode_token


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    res = await db.execute(select(User).where(User.email == payload.get("sub")))
    return res.scalar_one_or_none()


async def require_admin(user: Optional[User] = Depends(get_current_user)) -> User:
    if not user or not user.is_admin or not user.is_active:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER,
                            headers={"Location": "/admin/login"})
    return user
