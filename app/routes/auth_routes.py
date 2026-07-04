"""دخول وخروج المدير."""
from fastapi import APIRouter, Request, Form, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.models.user import User
from app.core.security import verify_password, create_access_token
from app.utils.templates import templates

from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/admin/login")
async def login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})


@router.post("/admin/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...),
                db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == email.strip().lower()))).scalar_one_or_none()
    if not user or not user.is_admin or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("admin/login.html",
                                          {"request": request, "error": "بيانات غير صحيحة"},
                                          status_code=400)
    token = create_access_token(user.email, {"uid": user.id})
    resp = RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie("access_token", token, httponly=True, samesite="lax",
                    secure=False, max_age=60 * 60 * 4, path="/")
    return resp


@router.get("/admin/logout")
async def logout():
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie("access_token", path="/")
    return resp


@router.post("/api/quick-login")
async def quick_login(request: Request, email: str = Form(...), password: str = Form(...),
                      db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == email.strip().lower()))).scalar_one_or_none()
    if not user or not user.is_admin or not verify_password(password, user.hashed_password):
        return JSONResponse({"ok": False, "error": "البريد أو كلمة المرور غير صحيحة"}, status_code=401)
    token = create_access_token(user.email, {"uid": user.id})
    resp = JSONResponse({"ok": True})
    resp.set_cookie("access_token", token, httponly=True, samesite="lax",
                    secure=False, max_age=60 * 60 * 4, path="/")
    return resp
