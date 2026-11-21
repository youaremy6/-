"""Offline rewrite provider: preset pack first, conservative lexicon second.

The rule fallback is intentionally narrow.  Unknown wording is passed through
unchanged with a lowered confidence and the touched words listed as uncertain,
instead of inventing dialect phrasing.
"""

from __future__ import annotations

from . import lexicon
from .base import DialectResult, MandarinResult
from .phrases import PhraseRepository


class MockLLM:
    name = "mock"
    mode = "mock"

    def __init__(self, phrases: PhraseRepository) -> None:
        self._phrases = phrases

    async def to_mandarin(self, text: str, *, scenario: str | None = None) -> MandarinResult:
        phrase = self._phrases.find_by_text(text, "lanzhou")
        if phrase is not None:
            return MandarinResult(
                normalized_mandarin=phrase.mandarin,
                confidence=0.92,
                uncertain_words=[],
                needs_confirmation=False,
            )
        normalized, uncertain = lexicon.to_mandarin(text)
        confidence = 0.62 if uncertain else 0.72
        return MandarinResult(
            normalized_mandarin=normalized,
            confidence=confidence,
            uncertain_words=uncertain,
            needs_confirmation=confidence < 0.7,
        )

    async def to_dialect(self, text: str, *, scenario: str | None = None) -> DialectResult:
        phrase = self._phrases.find_by_text(text, "mandarin")
        if phrase is not None:
            return DialectResult(
                dialect_text=phrase.lanzhou,
                back_translation=phrase.mandarin,
                confidence=0.9,
                uncertain_words=[],
                needs_confirmation=False,
            )
        dialect, uncertain = lexicon.to_lanzhou(text)
        confidence = 0.6 if uncertain else 0.7
        return DialectResult(
            dialect_text=dialect,
            back_translation=text,
            confidence=confidence,
            uncertain_words=uncertain,
            needs_confirmation=confidence < 0.7,
        )
