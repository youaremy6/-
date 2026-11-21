"""Provider-independent contracts shared by live and mock implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(Exception):
    """A dependency failed in a way the API must surface as a degraded result."""

    def __init__(self, code: str, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass
class ASRResult:
    text: str
    confidence: float
    provider: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class MandarinResult:
    normalized_mandarin: str
    confidence: float
    uncertain_words: list[str] = field(default_factory=list)
    needs_confirmation: bool = False


@dataclass
class DialectResult:
    dialect_text: str
    back_translation: str
    confidence: float
    uncertain_words: list[str] = field(default_factory=list)
    needs_confirmation: bool = False


@dataclass
class TTSResult:
    audio: bytes | None
    provider: str
    ext: str = ".wav"
    failure_reason: str | None = None


class ASRProvider(Protocol):
    name: str
    mode: str

    async def transcribe(
        self,
        pcm: bytes,
        sample_rate: int,
        *,
        scenario: str | None = None,
        hint_text: str | None = None,
    ) -> ASRResult: ...


class LLMProvider(Protocol):
    name: str
    mode: str

    async def to_mandarin(
        self, text: str, *, scenario: str | None = None
    ) -> MandarinResult: ...

    async def to_dialect(
        self, text: str, *, scenario: str | None = None
    ) -> DialectResult: ...


class TTSProvider(Protocol):
    name: str
    mode: str

    async def synthesize(
        self, text: str, *, mode: str = "dialect", request_id: str = ""
    ) -> TTSResult: ...
