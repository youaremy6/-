"""Privacy: delete the current session record and its generated audio."""

from __future__ import annotations

import re

from fastapi import APIRouter, Request

from ..models.schemas import REQUEST_ID_PATTERN
from .deps import get_container
from .errors import ApiError

router = APIRouter()
_ID_RE = re.compile(REQUEST_ID_PATTERN)


@router.delete("/records/{request_id}")
async def delete_record(request: Request, request_id: str):
    if not _ID_RE.match(request_id):
        raise ApiError(400, "invalid_request", "requestId 格式不正确。")
    container = get_container(request)
    record = container.records.delete(request_id)
    if record is None:
        raise ApiError(404, "record_not_found", "没有找到这次记录，可能已经删除。")
    for key in record.get("mediaKeys", []):
        container.media.delete(key)
    container.idempotency.pop(request_id)
    return {"deleted": True, "requestId": request_id}
