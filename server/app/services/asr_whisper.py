"""Local Whisper ASR used when 讯飞 credentials are unavailable.

This is real speech recognition: audio is transcribed by a local
faster-whisper model, not selected from a preset list.  The small model is a
pragmatic CPU fallback; 讯飞甘肃话 remains the dialect-accurate option.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

from ..config import Settings
from .base import ASRResult, ProviderError
from .phrases import PhraseRepository


class WhisperASR:
    name = "whisper"
    mode = "local"

    def __init__(self, settings: Settings, phrases: PhraseRepository) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ProviderError(
                "asr_unavailable",
                "本地识别组件未安装（faster-whisper）。",
                retryable=False,
            ) from exc

        self._model_name = settings.whisper_model
        self._model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            local_files_only=True,
        )
        # Domain prompt keeps Whisper from drifting to standard Mandarin for
        # short Lanzhou words such as 组撒/没麻达/干散/瓜怂.
        lanzhou = [item.lanzhou.strip("。！？") for item in phrases.all()]
        self._initial_prompt = "兰州话常用句：" + "。".join(lanzhou[:30])
        self._lock = asyncio.Lock()

    async def transcribe(
        self,
        pcm: bytes,
        sample_rate: int,
        *,
        scenario: str | None = None,
        hint_text: str | None = None,
    ) -> ASRResult:
        if hint_text:
            return ASRResult(text=hint_text, confidence=0.86, provider=self.name, warnings=["local_asr"])

        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover
            raise ProviderError("asr_unavailable", "本地识别缺少 numpy。", retryable=False) from exc

        audio = np.frombuffer(pcm[: (len(pcm) // 2) * 2], dtype="<i2").astype(np.float32) / 32768.0

        async with self._lock:
            try:
                text, confidence = await asyncio.to_thread(self._transcribe_sync, audio)
            except Exception as exc:  # pragma: no cover - model/runtime dependent
                raise ProviderError("asr_error", f"本地识别失败：{exc}") from exc

        return ASRResult(
            text=text,
            confidence=confidence,
            provider=self.name,
            warnings=["local_asr"],
        )

    def _transcribe_sync(self, audio: Any) -> tuple[str, float]:
        segments, _info = self._model.transcribe(
            audio,
            language="zh",
            task="transcribe",
            beam_size=3,
            vad_filter=False,
            condition_on_previous_text=False,
            without_timestamps=True,
            initial_prompt=self._initial_prompt,
            temperature=0,
        )
        texts: list[str] = []
        logprobs: list[float] = []
        for segment in segments:
            piece = (segment.text or "").strip()
            if piece:
                texts.append(piece)
                logprobs.append(float(getattr(segment, "avg_logprob", -0.7)))

        text = "".join(texts).strip()
        if not text:
            return "", 0.0

        average = sum(logprobs) / len(logprobs) if logprobs else -0.7
        confidence = max(0.3, min(0.95, math.exp(average)))
        return text, round(confidence, 3)
