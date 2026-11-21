"""Wires settings, providers, caches and stores into one app-scoped object."""

from __future__ import annotations

import logging

from ..config import Settings
from .asr_mock import MockASR
from .asr_whisper import WhisperASR
from .asr_xfyun import XfyunASR
from .base import ASRProvider, LLMProvider, TTSProvider
from .cache import TTLCache
from .llm_mock import MockLLM
from .llm_translate import OpenAICompatibleLLM
from .phrases import PhraseRepository
from .storage import MediaStore
from .tts_cosyvoice import CosyVoiceTTS
from .tts_mock import MockTTS

logger = logging.getLogger("xiaogan.container")


class RecordStore:
    """Minimal non-content record store backing "删除本次记录" (spec 8.2).

    Only identifiers and media keys are kept; original/translated text and
    input audio are deliberately never persisted.
    """

    def __init__(self) -> None:
        self._records: dict[str, dict] = {}

    def put(self, request_id: str, **fields) -> None:
        if len(self._records) >= 2000 and request_id not in self._records:
            oldest = next(iter(self._records))
            self._records.pop(oldest, None)
        self._records[request_id] = fields

    def get(self, request_id: str) -> dict | None:
        return self._records.get(request_id)

    def delete(self, request_id: str) -> dict | None:
        return self._records.pop(request_id, None)

    def __len__(self) -> int:
        return len(self._records)


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.phrases = PhraseRepository(
            pack_path=settings.phrase_asset_dir / "phrases.json",
            asset_dir=settings.phrase_asset_dir,
            public_base_url=settings.public_base_url,
        )
        if not self.phrases.loaded:
            logger.warning("phrase pack unavailable: %s", self.phrases.load_error)

        secret = settings.signing_secret()
        self.media = MediaStore(
            media_dir=settings.media_dir,
            signing_secret=secret,
            public_base_url=settings.public_base_url,
            default_ttl_seconds=settings.media_ttl_seconds,
        )
        self.cache = TTLCache(
            ttl_seconds=settings.cache_ttl_seconds, max_entries=settings.cache_max_entries
        )
        self.idempotency = TTLCache(ttl_seconds=3600, max_entries=2000)
        self.records = RecordStore()
        self._locks: dict[str, object] = {}

        if settings.use_live("asr"):
            asr_provider = XfyunASR(settings)
        elif settings.use_whisper():
            try:
                asr_provider = WhisperASR(settings, self.phrases)
            except Exception as exc:  # model/package unavailable -> keep demo usable
                logger.warning("local Whisper unavailable, falling back to mock: %s", exc)
                asr_provider = MockASR(self.phrases)
        else:
            asr_provider = MockASR(self.phrases)
        self.asr: ASRProvider = asr_provider
        self.llm: LLMProvider = (
            OpenAICompatibleLLM(settings) if settings.use_live("llm") else MockLLM(self.phrases)
        )
        self.tts: TTSProvider = (
            CosyVoiceTTS(settings) if settings.use_live("tts") else MockTTS(self.phrases)
        )

        logger.info(
            "providers asr=%s llm=%s tts=%s mode=%s",
            self.asr.name,
            self.llm.name,
            self.tts.name,
            settings.provider_mode,
        )

    def get_lock(self, request_id: str):
        """One asyncio.Lock per in-flight requestId (duplicate-tap protection)."""
        import asyncio

        lock = self._locks.get(request_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[request_id] = lock
        return lock

    def provider_modes(self) -> dict[str, str]:
        return {"asr": self.asr.mode, "llm": self.llm.mode, "tts": self.tts.mode}

    def all_mock(self) -> bool:
        return self.asr.mode == "mock" and self.llm.mode == "mock" and self.tts.mode == "mock"
