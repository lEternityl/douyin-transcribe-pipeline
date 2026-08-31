"""Cookie 路由:上传/状态。"""
from fastapi import APIRouter

from app.schemas import CookieRequest, CookieStatus
from app.services.cookie import cookie_status, save_cookie

router = APIRouter(prefix="/api/cookie", tags=["cookie"])


@router.get("/status", response_model=CookieStatus)
def status() -> CookieStatus:
    return CookieStatus(**cookie_status())


@router.post("", response_model=CookieStatus)
def set_cookie(payload: CookieRequest) -> CookieStatus:
    save_cookie(payload.content)
    return CookieStatus(**cookie_status())
