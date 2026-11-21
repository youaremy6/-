"""Offline ASR used when 讯飞 credentials are not configured.

It is *not* speech recognition: it deterministically picks a preset Lanzhou
sentence so the rest of the pipeline (LLM -> TTS -> result card) stays
exercisable.  Every result carries the ``mock_asr`` warning and the mini
program shows a demo-mode banner, so it can never be mistaken for a real
transcript during a demo.

The mock skips leading silence before hashing.  Recordings start with 50-300 ms
of silence while the OS/browser brings the microphone up; hashing the first
2 KB therefore made every press-to-talk request resolve to the same preset
sentence (transport_04, "请问公交车站在阿达？").  The onset detector keeps the
demo varied for voiced input and returns an empty transcript for true silence.
"""

from __future__ import annotations

import array
import hashlib
import sys

from .base import ASRResult
from .phrases import PhraseRepository

_FRAME_SAMPLES = 320  # 20 ms at 16 kHz
_MIN_VOICED_RMS = 80  # 16-bit PCM; below this the whole clip is silence
_VOICED_RATIO = 0.12  # onset threshold relative to the loudest frame
_HASH_BYTES = 16_384  # 512 ms after onset


def _first_voiced_offset(pcm: bytes) -> int | None:
    """Return the byte offset of the first voiced 20 ms frame, or None."""
    if len(pcm) < _FRAME_SAMPLES * 2:
        return None

    samples = array.array("h")
    samples.frombytes(pcm[: (len(pcm) // 2) * 2])
    if sys.byteorder != "little":
        samples.byteswap()

    frames: list[tuple[int, float]] = []
    for start in range(0, len(samples) - _FRAME_SAMPLES + 1, _FRAME_SAMPLES):
        chunk = samples[start : start + _FRAME_SAMPLES]
        energy = sum(value * value for value in chunk) / len(chunk)
        frames.append((start, energy**0.5))

    if not frames:
        return None

    peak = max(rms for _, rms in frames)
    if peak < _MIN_VOICED_RMS:
        return None

    threshold = max(_MIN_VOICED_RMS, peak * _VOICED_RATIO)
    for start, rms in frames:
        if rms >= threshold:
            return start * 2
    return None


class MockASR:
    name = "mock"
    mode = "mock"

    def __init__(self, phrases: PhraseRepository) -> None:
        self._phrases = phrases

    async def transcribe(
        self,
        pcm: bytes,
        sample_rate: int,
        *,
        scenario: str | None = None,
        hint_text: str | None = None,
    ) -> ASRResult:
        if hint_text:
            return ASRResult(text=hint_text, confidence=0.86, provider=self.name, warnings=["mock_asr"])
        pool = self._phrases.list(scenario) or self._phrases.all()
        if not pool:
            return ASRResult(text="", confidence=0.0, provider=self.name, warnings=["mock_asr"])

        onset = _first_voiced_offset(pcm)
        if onset is None:
            return ASRResult(
                text="",
                confidence=0.0,
                provider=self.name,
                warnings=["mock_asr", "silence"],
            )

        payload = pcm[onset : onset + _HASH_BYTES] or pcm[onset:] or b"empty"
        digest = hashlib.sha256(payload).digest()
        index = int.from_bytes(digest[:4], "big") % len(pool)
        return ASRResult(
            text=pool[index].lanzhou,
            confidence=0.86,
            provider=self.name,
            warnings=["mock_asr", "voiced_mock"],
        )
