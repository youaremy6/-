"""Endpoint tests for POST /api/v1/translate/audio (spec 5.4, 10.1)."""

from __future__ import annotations

import pytest

from app.services.base import ASRResult
from tests.helpers import pcm_bytes, signed_path, upload


def test_happy_path_returns_transcript_translation_and_audio(client, pack):
    response = upload(client, pcm_bytes(1.0), requestId="req_audio_0001")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["direction"] == "dialect_to_mandarin"
    assert body["asrText"] in {item["lanzhou"] for item in pack["phrases"]}
    assert body["normalizedText"]
    assert body["translatedText"] == body["normalizedText"]
    assert body["outputText"]
    assert 0.0 <= body["confidence"] <= 1.0
    assert "mock_asr" in body["warnings"]
    assert body["latencyMs"] >= 0
    assert body["outputAudioUrl"]

    media = client.get(signed_path(body["outputAudioUrl"]))
    assert media.status_code == 200
    assert len(media.content) > 1000
    assert media.headers["content-type"] in {"audio/mpeg", "audio/wav"}


def test_rejects_too_short(client):
    response = upload(client, pcm_bytes(0.5), requestId="req_short_0001")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "too_short"


def test_rejects_non_pcm(client):
    payload = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 40_000
    response = upload(client, payload, requestId="req_mp3_00001")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_audio"


def test_rejects_empty_upload(client):
    response = upload(client, b"", requestId="req_empty_0001")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "empty_audio"


def test_rejects_oversized_upload(client):
    response = upload(client, b"\x00\x01" * 1_000_001, requestId="req_big_000001")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "audio_too_large"


def test_missing_request_id_is_invalid(client):
    response = client.post(
        "/api/v1/translate/audio",
        files={"audio": ("speech.pcm", pcm_bytes(1.0), "application/octet-stream")},
        data={"dialectId": "lanzhou"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_unsupported_dialect(client):
    response = upload(client, pcm_bytes(1.0), requestId="req_dial_0001", dialectId="tianshui")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_dialect"


def test_invalid_scenario(client):
    response = upload(client, pcm_bytes(1.0), requestId="req_scen_0001", scenario="hospital")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_scenario"


def test_idempotent_replay(client):
    container = client.app.state.container
    calls = {"count": 0}
    real = container.asr

    class CountingASR:
        name = real.name
        mode = real.mode

        async def transcribe(self, pcm, sample_rate, **kwargs):
            calls["count"] += 1
            return await real.transcribe(pcm, sample_rate, **kwargs)

    container.asr = CountingASR()

    first = upload(client, pcm_bytes(1.0), requestId="req_idem_00001")
    second = upload(client, pcm_bytes(1.0), requestId="req_idem_00001")
    assert first.status_code == second.status_code == 200
    assert calls["count"] == 1
    assert second.json()["cached"] is True
    assert second.json()["asrText"] == first.json()["asrText"]
    assert second.json()["outputAudioUrl"] == first.json()["outputAudioUrl"]


def test_empty_asr_is_reported(client):
    response = upload(
        client,
        pcm_bytes(1.0),
        requestId="req_asrempty1",
        headers={"x-mock-behavior": "asr_empty"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "asr_empty"
    assert error["retryable"] is True


def test_silence_is_not_forced_to_a_preset_sentence(client):
    response = upload(client, b"\x00" * 32_000, requestId="req_silence_01")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "asr_empty"


def test_leading_silence_still_yields_a_mock_transcript(client, pack):
    payload = b"\x00" * 16_000 + pcm_bytes(1.0)
    response = upload(client, payload, requestId="req_lead_sil_1")
    assert response.status_code == 200, response.text
    assert response.json()["asrText"] in {item["lanzhou"] for item in pack["phrases"]}


def test_low_confidence_blocks_translation(client):
    response = upload(
        client,
        pcm_bytes(1.0),
        requestId="req_asrlow_01",
        headers={"x-mock-behavior": "asr_low"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "low_confidence"
    assert error["details"]["asrText"]


def test_tts_failure_degrades_to_text(client):
    response = upload(
        client,
        pcm_bytes(1.0),
        requestId="req_ttsfail1",
        headers={"x-mock-behavior": "tts_error"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "tts_error" in body["warnings"]
    assert body["outputAudioUrl"] is None
    assert body["translatedText"]


def test_llm_failure_degrades_to_transcript(client):
    response = upload(
        client,
        pcm_bytes(1.0),
        requestId="req_llmfail1",
        headers={"x-mock-behavior": "llm_error"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "llm_degraded" in body["warnings"]
    assert body["normalizedText"] == body["asrText"]
    assert body["needsConfirmation"] is True


def test_medium_confidence_keeps_result_but_warns(client):
    container = client.app.state.container

    class MediumASR:
        name = "mock"
        mode = "mock"

        async def transcribe(self, pcm, sample_rate, **kwargs):
            return ASRResult(
                text="大夫，我脑壳有点晕。", confidence=0.6, provider="mock", warnings=["mock_asr"]
            )

    container.asr = MediumASR()
    response = upload(client, pcm_bytes(1.0), requestId="req_midconf1")
    assert response.status_code == 200
    body = response.json()
    assert body["needsConfirmation"] is True
    assert "low_confidence" in body["warnings"]


@pytest.mark.parametrize("bad_id", ["short", "bad id", "abc!", "x" * 65])
def test_invalid_request_id(client, bad_id):
    response = upload(client, pcm_bytes(1.0), requestId=bad_id)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
