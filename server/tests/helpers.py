"""Shared test helpers."""

from __future__ import annotations

from fastapi.testclient import TestClient


def pcm_bytes(seconds: float = 1.0, amplitude: int = 1200) -> bytes:
    frames = int(16_000 * seconds)
    return (amplitude.to_bytes(2, "little", signed=True)) * frames


def upload(client: TestClient, data: bytes, *, headers: dict | None = None, **form):
    payload = {"requestId": "req_test_0001", "dialectId": "lanzhou", "scenario": "medical"}
    payload.update(form)
    return client.post(
        "/api/v1/translate/audio",
        files={"audio": ("speech.pcm", data, "application/octet-stream")},
        data=payload,
        headers=headers,
    )


def signed_path(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return f"{parsed.path}?{parsed.query}"
