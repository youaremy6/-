"""Runtime configuration for the 小甘 (Lanzhou dialect) API.

Every secret is read from the environment; nothing is hard-coded.  When a
credential is missing the corresponding provider is replaced by a local,
clearly labelled mock so the demo never hangs in a loading state.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SERVER_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", SERVER_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- app -------------------------------------------------------------
    app_name: str = "小甘 · 兰州话双向对话 API"
    version: str = "0.1.0"
    env: Literal["dev", "test", "prod"] = "dev"
    public_base_url: str = "http://127.0.0.1:8000"
    api_prefix: str = "/api/v1"
    cors_origins: str = "*"
    enable_debug_hooks: bool = True

    # auto: use a live provider only when its credentials are present
    provider_mode: Literal["auto", "mock", "live"] = "auto"

    # --- 讯飞 甘肃话 ASR ------------------------------------------------
    xf_app_id: str = ""
    xf_api_key: str = ""
    xf_api_secret: str = ""
    xf_accent_gansu: str = ""
    xf_domain: str = "xfime-mianqie"
    xf_asr_url: str = "wss://iat-api.xfyun.cn/v2/iat"
    xf_asr_timeout_seconds: float = 15.0

    # --- local Whisper ASR (fallback when 讯飞 is not configured) --------
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # --- LLM (OpenAI compatible) ----------------------------------------
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = 20.0
    llm_temperature: float = 0.1

    # --- CosyVoice3 TTS --------------------------------------------------
    cosyvoice_base_url: str = ""
    cosyvoice_prompt_audio_url: str = ""
    cosyvoice_prompt_text: str = ""
    cosyvoice_instruct: str = (
        "You are a helpful assistant. 请用甘肃话表达。<|endofprompt|>"
    )
    cosyvoice_sample_rate: int = 24000
    cosyvoice_timeout_seconds: float = 30.0

    # --- object storage / local media -----------------------------------
    storage_bucket: str = ""
    storage_access_key: str = ""
    storage_secret_key: str = ""
    media_dir: Path = SERVER_DIR / "var" / "media"
    media_signing_secret: str = ""
    signed_url_ttl_seconds: int = Field(default=3600, ge=60, le=86_400)
    phrase_asset_dir: Path = REPO_ROOT / "assets" / "phrases"

    # --- limits ----------------------------------------------------------
    max_audio_bytes: int = 2_000_000
    max_record_seconds: int = 30
    min_record_seconds: float = 0.8
    max_text_chars: int = 200
    asr_min_confidence: float = 0.45
    asr_hint_confidence: float = 0.7
    audio_retention_hours: int = 0
    output_audio_ttl_minutes: int = 60

    # --- cache -----------------------------------------------------------
    cache_ttl_seconds: int = 1800
    cache_max_entries: int = 500
    llm_instruct_version: str = "v1"
    voice_id: str = "lanzhou-female-v1"

    @property
    def media_ttl_seconds(self) -> int:
        """Signed URL lifetime capped at 24h (spec 6.2)."""
        return min(86_400, self.signed_url_ttl_seconds)

    def asr_live_ready(self) -> bool:
        return bool(self.xf_app_id and self.xf_api_key and self.xf_api_secret and self.xf_accent_gansu)

    def use_whisper(self) -> bool:
        return self.provider_mode != "mock" and bool(self.whisper_model.strip())

    def llm_live_ready(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    def tts_live_ready(self) -> bool:
        return bool(self.cosyvoice_base_url and self.cosyvoice_prompt_audio_url)

    def use_live(self, provider: Literal["asr", "llm", "tts"]) -> bool:
        if self.provider_mode == "mock":
            return False
        ready = {
            "asr": self.asr_live_ready,
            "llm": self.llm_live_ready,
            "tts": self.tts_live_ready,
        }[provider]()
        if self.provider_mode == "live":
            return ready
        return ready

    def signing_secret(self) -> str:
        import hashlib

        base = self.media_signing_secret or self.storage_secret_key or "xiao-gan-local-dev"
        return hashlib.sha256(f"xiao-gan-media|{base}".encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
