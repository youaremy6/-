"""Endpoint tests for POST /api/v1/translate/text (spec 5.4, 7.4)."""

from __future__ import annotations

from tests.helpers import signed_path


def _post(client, *, headers: dict | None = None, **body):
    payload = {
        "requestId": "req_text_0001",
        "direction": "mandarin_to_dialect",
        "dialectId": "lanzhou",
        "scenario": "medical",
        "text": "医生，我有点头晕。",
    }
    payload.update(body)
    return client.post("/api/v1/translate/text", json=payload, headers=headers)


def test_phrase_hit_returns_dialect_text_and_audio(client, pack):
    response = _post(client, requestId="req_text_0001")
    assert response.status_code == 200, response.text
    body = response.json()

    phrase = next(p for p in pack["phrases"] if p["mandarin"] == "医生，我有点头晕。")
    assert body["inputText"] == "医生，我有点头晕。"
    assert body["dialectText"] == phrase["lanzhou"]
    assert body["backTranslation"]
    assert body["ttsProvider"] == "phrase_pack"
    assert "cached_phrase" in body["warnings"]
    assert body["outputAudioUrl"]

    media = client.get(signed_path(body["outputAudioUrl"]))
    assert media.status_code == 200
    assert len(media.content) > 1000


def test_numbers_are_preserved(client):
    response = _post(
        client,
        requestId="req_text_0002",
        text="这个药28块5，一天吃3次。",
    )
    assert response.status_code == 200
    body = response.json()
    assert "28" in body["dialectText"]
    assert "3" in body["dialectText"]
    assert "numbers_changed" not in body["warnings"]


def test_dropped_numbers_are_flagged(client):
    from app.services.base import DialectResult

    container = client.app.state.container

    class DroppingLLM:
        name = "mock"
        mode = "mock"

        async def to_dialect(self, text, *, scenario=None):
            return DialectResult(
                dialect_text="这个药一天吃三回。",
                back_translation="这个药一天吃三次。",
                confidence=0.9,
                uncertain_words=[],
                needs_confirmation=False,
            )

        async def to_mandarin(self, text, *, scenario=None):  # pragma: no cover
            raise AssertionError("not used")

    container.llm = DroppingLLM()
    response = _post(client, requestId="req_text_0011", text="这个药28块5，一天吃3次。")
    assert response.status_code == 200
    body = response.json()
    assert "numbers_changed" in body["warnings"]
    assert body["needsConfirmation"] is True


def test_unknown_text_degrades_to_text_only(client):
    response = _post(client, requestId="req_text_0003", text="请问最近的地铁站在哪边？")
    assert response.status_code == 200
    body = response.json()
    assert body["dialectText"]
    assert body["outputAudioUrl"] is None
    assert "tts_error" in body["warnings"]


def test_rejects_wrong_direction(client):
    response = _post(client, requestId="req_text_0004", direction="dialect_to_mandarin")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_direction"


def test_rejects_non_lanzhou(client):
    response = _post(client, requestId="req_text_0005", dialectId="tianshui")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_rejects_blank_text(client):
    response = _post(client, requestId="req_text_0006", text="   ")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_rejects_overlong_text(client):
    response = _post(client, requestId="req_text_0007", text="啊" * 201)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_llm_failure_degrades(client):
    response = _post(
        client, requestId="req_text_0008", headers={"x-mock-behavior": "llm_error"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "llm_degraded" in body["warnings"]
    assert body["dialectText"] == body["inputText"]
    assert body["outputAudioUrl"] is None
    assert "text_only" in body["warnings"]
    assert body["needsConfirmation"] is True


def test_tts_failure_keeps_text(client):
    response = _post(client, requestId="req_text_0009", headers={"x-mock-behavior": "tts_error"})
    assert response.status_code == 200
    body = response.json()
    assert "tts_error" in body["warnings"]
    assert body["outputAudioUrl"] is None
    assert body["dialectText"]


def test_idempotent_replay(client):
    first = _post(client, requestId="req_text_0010")
    second = _post(client, requestId="req_text_0010")
    assert first.status_code == second.status_code == 200
    assert second.json()["cached"] is True
    assert "idempotent_replay" in second.json()["warnings"]
    assert second.json()["dialectText"] == first.json()["dialectText"]


def _post_dialect_text(client, *, headers: dict | None = None, **body):
    payload = {
        "requestId": "req_dtext_0001",
        "dialectId": "lanzhou",
        "scenario": "medical",
        "text": "大夫，我脑壳有点晕。",
    }
    payload.update(body)
    return client.post("/api/v1/translate/dialect-text", json=payload, headers=headers)


def test_corrected_transcript_returns_mandarin_and_audio(client):
    response = _post_dialect_text(client, requestId="req_dtext_0001")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["direction"] == "dialect_to_mandarin"
    assert body["inputText"] == "大夫，我脑壳有点晕。"
    assert body["normalizedText"] == "医生，我有点头晕。"
    assert body["outputText"] == body["translatedText"]
    assert body["ttsProvider"] == "phrase_pack"
    assert body["outputAudioUrl"]

    media = client.get(signed_path(body["outputAudioUrl"]))
    assert media.status_code == 200
    assert len(media.content) > 1000


def test_corrected_transcript_without_pack_audio_degrades(client):
    response = _post_dialect_text(
        client, requestId="req_dtext_0002", text="我今儿个不去上班了"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["normalizedText"]
    assert body["outputAudioUrl"] is None
    assert "tts_error" in body["warnings"]


def test_corrected_transcript_llm_failure(client):
    response = _post_dialect_text(
        client,
        requestId="req_dtext_0003",
        headers={"x-mock-behavior": "llm_error"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "llm_degraded" in body["warnings"]
    assert body["normalizedText"] == body["inputText"]
    assert body["needsConfirmation"] is True


def test_corrected_transcript_rejects_other_dialect(client):
    response = _post_dialect_text(client, requestId="req_dtext_0004", dialectId="tianshui")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_corrected_transcript_rejects_blank(client):
    response = _post_dialect_text(client, requestId="req_dtext_0005", text="  ")
    assert response.status_code == 400


def test_corrected_transcript_idempotent(client):
    first = _post_dialect_text(client, requestId="req_dtext_0006")
    second = _post_dialect_text(client, requestId="req_dtext_0006")
    assert second.status_code == 200
    assert second.json()["cached"] is True
    assert second.json()["normalizedText"] == first.json()["normalizedText"]
