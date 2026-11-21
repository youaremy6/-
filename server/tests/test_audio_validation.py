"""Unit tests for PCM/WAV validation (spec 6.2, 10.1)."""

from __future__ import annotations

import io
import wave

import pytest

from app.utils.audio import AudioError, validate_audio, wrap_wav
from tests.helpers import pcm_bytes


def test_accepts_raw_pcm() -> None:
    info = validate_audio(pcm_bytes(1.0))
    assert info.container == "pcm"
    assert info.sample_rate == 16_000
    assert info.channels == 1
    assert 0.99 < info.duration_s < 1.01


def test_accepts_wav_container() -> None:
    info = validate_audio(wrap_wav(pcm_bytes(1.2), 16_000))
    assert info.container == "wav"
    assert 1.19 < info.duration_s < 1.21


def test_rejects_empty() -> None:
    with pytest.raises(AudioError) as exc:
        validate_audio(b"")
    assert exc.value.code == "empty_audio"
    assert exc.value.status_code == 400


def test_rejects_too_short() -> None:
    with pytest.raises(AudioError) as exc:
        validate_audio(pcm_bytes(0.5))
    assert exc.value.code == "too_short"
    assert exc.value.status_code == 422


def test_rejects_too_long() -> None:
    with pytest.raises(AudioError) as exc:
        validate_audio(pcm_bytes(31.0))
    assert exc.value.code == "too_long"
    assert exc.value.status_code == 422


def test_rejects_mp3() -> None:
    payload = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 40_000
    with pytest.raises(AudioError) as exc:
        validate_audio(payload)
    assert exc.value.code == "unsupported_audio"
    assert exc.value.status_code == 415


def test_rejects_oversized() -> None:
    with pytest.raises(AudioError) as exc:
        validate_audio(b"\x00\x01" * 1_000_001)
    assert exc.value.code == "audio_too_large"
    assert exc.value.status_code == 413


def test_rejects_stereo_wav() -> None:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(pcm_bytes(1.0) * 2)
    with pytest.raises(AudioError) as exc:
        validate_audio(buffer.getvalue())
    assert exc.value.code == "unsupported_audio"


def test_rejects_wrong_sample_rate() -> None:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8_000)
        wav.writeframes(b"\x00\x01" * 8_000)
    with pytest.raises(AudioError) as exc:
        validate_audio(buffer.getvalue())
    assert exc.value.code == "unsupported_audio"
