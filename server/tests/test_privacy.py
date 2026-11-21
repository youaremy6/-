"""Privacy, idempotency and cache-key tests (spec 8.2, 10.1)."""

from __future__ import annotations

import logging

from app.api.routes_translate import _build_cache_key
from app.services.cache import TTLCache
from tests.helpers import pcm_bytes, upload

SECRET_TEXT = "隐私检查专用句子七十三号"


def test_logs_never_contain_original_text(client, caplog):
    records: list[str] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = Collector()
    logging.getLogger().addHandler(handler)
    try:
        with caplog.at_level(logging.INFO):
            response = client.post(
                "/api/v1/translate/text",
                json={
                    "requestId": "req_privacy_01",
                    "direction": "mandarin_to_dialect",
                    "dialectId": "lanzhou",
                    "text": SECRET_TEXT,
                },
            )
    finally:
        logging.getLogger().removeHandler(handler)

    assert response.status_code == 200
    joined = "\n".join(records)
    assert SECRET_TEXT not in joined
    assert all(len(line) < 500 for line in records)


def test_input_audio_is_not_persisted(client, app):
    response = upload(client, pcm_bytes(1.0), requestId="req_privacy_02")
    assert response.status_code == 200
    container = app.state.container
    leftovers = [p.name for p in container.media.media_dir.iterdir()]
    assert leftovers, "generated output audio should exist for playback"
    assert not any(name.endswith((".pcm", ".raw", ".tmp")) for name in leftovers)


def test_request_id_is_echoed(client):
    response = upload(
        client, pcm_bytes(1.0), requestId="req_echo_0001", headers={"x-request-id": "hdr-123456"}
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "hdr-123456"


def test_cache_key_is_stable_and_scoped():
    class FakeSettings:
        voice_id = "lanzhou-female-v1"
        llm_instruct_version = "v1"

    settings = FakeSettings()
    first = _build_cache_key(settings, "医生，我头晕。", "mandarin")
    second = _build_cache_key(settings, "医生，我头晕。", "mandarin")
    other_text = _build_cache_key(settings, "医生，我头疼。", "mandarin")
    other_mode = _build_cache_key(settings, "医生，我头晕。", "dialect")
    assert first == second
    assert first != other_text
    assert first != other_mode
    assert len(first) == 64


def test_ttl_cache_expires():
    cache = TTLCache(ttl_seconds=0, max_entries=2)
    cache.set("a", 1)
    assert cache.get("a") is None
    cache.set("b", 2, ttl_seconds=60)
    assert cache.get("b") == 2
