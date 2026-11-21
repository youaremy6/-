"""Dependency accessors and per-request safe helpers."""

from __future__ import annotations

from fastapi import Request

from ..config import Settings
from ..services.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_settings(request: Request) -> Settings:
    return request.app.state.container.settings


def debug_behavior(request: Request) -> str | None:
    """Dev-only failure injection, e.g. ``X-Mock-Behavior: asr_empty``.

    Disabled automatically when ``ENV=prod``; used by the failure-injection
    test matrix and manual QA (spec 10.3).
    """
    container = get_container(request)
    if container.settings.env == "prod" or not container.settings.enable_debug_hooks:
        return None
    return request.headers.get("x-mock-behavior")
