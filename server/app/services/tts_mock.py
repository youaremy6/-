"""Offline TTS: returns the bundled native-review *placeholder* audio.

No audio is ever fabricated for text outside the phrase pack; callers fall
back to a text-only result instead, which is the degradation the spec asks for
("反向只保留文字 + 预设语音包").
"""

from __future__ import annotations

from .base import TTSResult
from .phrases import PhraseRepository


class MockTTS:
    name = "phrase_pack"
    mode = "mock"

    def __init__(self, phrases: PhraseRepository) -> None:
        self._phrases = phrases

    async def synthesize(
        self, text: str, *, mode: str = "dialect", request_id: str = ""
    ) -> TTSResult:
        language = "lanzhou" if mode == "dialect" else "mandarin"
        phrase = self._phrases.find_by_text(text, language)
        if phrase is None:
            return TTSResult(
                audio=None,
                provider=self.name,
                failure_reason="tts_phrase_not_found",
            )
        audio = self._phrases.audio_bytes(phrase, language)
        if audio is None:
            return TTSResult(audio=None, provider=self.name, failure_reason="tts_asset_missing")
        suffix = self._phrases.audio_path(phrase, language)
        ext = suffix.suffix if suffix else ".mp3"
        return TTSResult(audio=audio, provider=self.name, ext=ext)
