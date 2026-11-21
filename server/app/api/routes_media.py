"""Short-lived signed media URLs for generated audio (spec 6.2)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from .deps import get_container
from .errors import ApiError

router = APIRouter()


@router.get("/media/{key}")
async def get_media(request: Request, key: str, exp: int = 0, sig: str = ""):
    container = get_container(request)
    if not container.media.verify(key, exp, sig):
        raise ApiError(403, "media_forbidden", "链接已过期或签名无效。")
    path = container.media.path(key)
    if not path.exists():
        raise ApiError(404, "media_not_found", "音频已过期或被删除。")
    return FileResponse(
        path,
        media_type=container.media.content_type(key),
        headers={"Cache-Control": "private, max-age=300"},
    )
