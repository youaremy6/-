"""Preset phrases and their bundled audio (public product content)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..models.schemas import PhraseListResponse, Scenario
from .deps import get_container
from .errors import ApiError

router = APIRouter()


@router.get("/phrases", response_model=PhraseListResponse)
async def list_phrases(request: Request, scenario: str | None = None):
    container = get_container(request)
    if not container.phrases.loaded:
        raise ApiError(
            503,
            "phrase_pack_unavailable",
            "常用句语音包没有加载，请检查 assets/phrases/phrases.json。",
            retryable=True,
        )
    if scenario is not None:
        try:
            scenario = Scenario(scenario).value
        except ValueError as exc:
            raise ApiError(
                400, "invalid_scenario", "scenario 只能是 medical / transport / market / help。"
            ) from exc
    return container.phrases.to_api_list(scenario)
