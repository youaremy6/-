"""Dependency status for the pre-demo check (spec 5.4 GET /health)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..models.schemas import HealthDependency, HealthResponse
from .deps import get_container

router = APIRouter()


def _dependency(
    *,
    live_ready: bool,
    provider_name: str,
    force_mock: bool,
    mock_detail: str,
) -> HealthDependency:
    if force_mock:
        return HealthDependency(ok=True, provider="mock", mode="mock", detail=mock_detail)
    if live_ready:
        return HealthDependency(ok=True, provider=provider_name, mode="live", detail=None)
    return HealthDependency(
        ok=False,
        provider=provider_name,
        mode="misconfigured",
        detail=mock_detail,
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    container = get_container(request)
    settings = container.settings

    dependencies: dict[str, HealthDependency] = {}
    if container.asr.mode == "local":
        dependencies["asr"] = HealthDependency(
            ok=True,
            provider=container.asr.name,
            mode="local",
            detail="本地 Whisper 识别（通用中文模型，非甘肃话专用）。",
        )
    else:
        dependencies["asr"] = _dependency(
            live_ready=settings.asr_live_ready(),
            provider_name="xfyun",
            force_mock=container.asr.mode == "mock",
            mock_detail="未配置讯飞 ASR 凭据，使用内置演示转写（不是真实识别）。",
        )
    dependencies["llm"] = _dependency(
        live_ready=settings.llm_live_ready(),
        provider_name="openai-compatible",
        force_mock=container.llm.mode == "mock",
        mock_detail="未配置 LLM，使用内置词表改写（草稿）。",
    )
    dependencies["tts"] = _dependency(
        live_ready=settings.tts_live_ready(),
        provider_name="cosyvoice3",
        force_mock=container.tts.mode == "mock",
        mock_detail="未配置 CosyVoice3，只播放预设语音包；其他文本仅返回文字。",
    )

    storage_ok = False
    try:
        probe = container.media.media_dir / ".health-probe"
        probe.write_bytes(b"ok")
        probe.unlink(missing_ok=True)
        storage_ok = True
    except OSError:
        storage_ok = False
    dependencies["storage"] = HealthDependency(
        ok=storage_ok,
        provider="local-media",
        mode="live" if storage_ok else "error",
        detail=None if storage_ok else "本地媒体目录不可写。",
    )
    dependencies["phrases"] = HealthDependency(
        ok=container.phrases.loaded,
        provider="phrase-pack",
        mode="live" if container.phrases.loaded else "error",
        detail=None
        if container.phrases.loaded
        else (container.phrases.load_error or "常用句语音包未加载。"),
    )

    all_live = all(dep.mode == "live" for dep in dependencies.values())
    all_ok = all(dep.ok for dep in dependencies.values())
    status = "ok" if all_live else ("degraded" if all_ok else "error")

    return HealthResponse(
        status=status,
        version=settings.version,
        env=settings.env,
        dialect="lanzhou（试运行）",
        dependencies=dependencies,
        limits={
            "maxAudioBytes": settings.max_audio_bytes,
            "maxRecordSeconds": settings.max_record_seconds,
            "minRecordSeconds": settings.min_record_seconds,
            "maxTextChars": settings.max_text_chars,
            "asrMinConfidence": settings.asr_min_confidence,
            "asrHintConfidence": settings.asr_hint_confidence,
            "signedUrlTtlSeconds": settings.media_ttl_seconds,
            "outputAudioTtlMinutes": settings.output_audio_ttl_minutes,
            "phraseCount": len(container.phrases.all()),
            "phraseVersion": container.phrases.version,
        },
        privacy="录音只用于本次翻译，处理完即删除；日志不记录原文、译文和音频；生成语音链接默认 1 小时过期，可在设置页删除本次记录。",
    )
