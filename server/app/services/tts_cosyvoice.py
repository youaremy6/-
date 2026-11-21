"""CosyVoice3 ``inference_instruct2`` client.

The upstream FastAPI runtime accepts ``tts_text`` / ``instruct_text`` form
fields plus a ``prompt_wav`` file and streams header-less PCM.  We wrap that
PCM in a WAV container so the mini program can play it directly.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from ..config import Settings
from ..utils.audio import wrap_wav
from .base import ProviderError, TTSResult

_DIALECT_INSTRUCT = "You are a helpful assistant. 请用甘肃话表达。<|endofprompt|>"
_MANDARIN_INSTRUCT = "You are a helpful assistant. 请用标准普通话表达。<|endofprompt|>"


class CosyVoiceTTS:
    name = "cosyvoice3"
    mode = "live"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.cosyvoice_base_url.rstrip("/")
        self._prompt: bytes | None = None

    def _instruct(self, mode: str) -> str:
        if mode == "dialect":
            return self._settings.cosyvoice_instruct or _DIALECT_INSTRUCT
        return _MANDARIN_INSTRUCT

    async def _prompt_audio(self) -> bytes:
        if self._prompt is not None:
            return self._prompt
        source = self._settings.cosyvoice_prompt_audio_url
        if not source:
            raise ProviderError(
                "tts_prompt_unavailable", "未配置 COSYVOICE_PROMPT_AUDIO_URL（母语者参考音频）。"
            )
        if source.startswith(("http://", "https://")):
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.get(source)
                    response.raise_for_status()
                    self._prompt = response.content
            except httpx.HTTPError as exc:
                raise ProviderError("tts_prompt_unavailable", f"参考音频下载失败：{exc}") from exc
        else:
            path = Path(source)
            if not path.exists():
                raise ProviderError(
                    "tts_prompt_unavailable", "参考音频路径不存在，请配置 COSYVOICE_PROMPT_AUDIO_URL。"
                )
            self._prompt = path.read_bytes()
        return self._prompt

    async def synthesize(
        self, text: str, *, mode: str = "dialect", request_id: str = ""
    ) -> TTSResult:
        prompt = await self._prompt_audio()
        data = {
            "tts_text": text,
            "instruct_text": self._instruct(mode),
            "stream": "false",
        }
        try:
            async with httpx.AsyncClient(timeout=self._settings.cosyvoice_timeout_seconds) as client:
                response = await client.post(
                    f"{self._base}/inference_instruct2",
                    data=data,
                    files={"prompt_wav": ("prompt.wav", prompt, "audio/wav")},
                )
        except httpx.TimeoutException as exc:
            raise ProviderError("tts_timeout", "方言语音合成超时。") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("tts_upstream_error", f"方言语音合成请求失败：{exc}") from exc

        if response.status_code != 200:
            raise ProviderError(
                "tts_upstream_error", f"CosyVoice 返回 {response.status_code}。"
            )
        pcm = response.content
        if len(pcm) < 3_200:  # < 0.1 s of audio
            raise ProviderError("tts_empty", "CosyVoice 返回了空音频。")
        return TTSResult(
            audio=wrap_wav(pcm, self._settings.cosyvoice_sample_rate),
            provider=self.name,
            ext=".wav",
        )
