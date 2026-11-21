"""Core translation endpoints (spec 5.4) plus the 改字 helper endpoint.

Pipeline responsibilities are kept here so the audio path and the
"corrected transcript" path share exactly one normalization/TTS behaviour.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import Counter
from dataclasses import dataclass, field

from fastapi import APIRouter, File, Form, Request, UploadFile

from ..models.schemas import (
    REQUEST_ID_PATTERN,
    DialectTextRequest,
    DialectTextResponse,
    Direction,
    Scenario,
    TranslateAudioResponse,
    TranslateTextRequest,
    TranslateTextResponse,
)
from ..services.base import ProviderError, TTSResult
from ..utils.audio import AudioError, validate_audio
from .deps import debug_behavior, get_container
from .errors import ApiError

router = APIRouter()

_ID_RE = re.compile(REQUEST_ID_PATTERN)
_DEBUG_BEHAVIORS = {"asr_empty", "asr_low", "tts_error", "llm_error", "slow"}
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _numbers_lost(source: str, target: str) -> bool:
    """True when the rewrite dropped a number/amount the user actually said."""
    source_counts = Counter(_NUMBER_RE.findall(source or ""))
    target_counts = Counter(_NUMBER_RE.findall(target or ""))
    return any(target_counts[token] < count for token, count in source_counts.items())


def _validate_request_id(value: str) -> str:
    if not _ID_RE.match(value or ""):
        raise ApiError(
            400, "invalid_request", "requestId 必须是 6-64 位字母、数字、下划线或短横线。"
        )
    return value


def _parse_scenario(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return Scenario(value).value
    except ValueError as exc:
        raise ApiError(
            400, "invalid_scenario", "scenario 只能是 medical / transport / market / help。"
        ) from exc


def _build_cache_key(settings, text: str, mode: str) -> str:
    raw = f"lanzhou|{settings.voice_id}|{mode}|{text}|{settings.llm_instruct_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _synthesize_with_fallback(
    container, text: str, mode: str, request_id: str
) -> TTSResult | None:
    """TTS chain: configured provider -> cached phrase -> text only (spec 6.2)."""
    try:
        result = await container.tts.synthesize(text, mode=mode, request_id=request_id)
        if result.audio:
            return result
    except ProviderError:
        pass
    except Exception:  # noqa: BLE001 - degrade instead of failing the request
        pass

    language = "lanzhou" if mode == "dialect" else "mandarin"
    phrase = container.phrases.find_by_text(text, language)
    if phrase is not None:
        audio = container.phrases.audio_bytes(phrase, language)
        if audio:
            path = container.phrases.audio_path(phrase, language)
            return TTSResult(
                audio=audio,
                provider="phrase_pack",
                ext=path.suffix if path else ".mp3",
            )
    return None


@dataclass
class _DialectOutput:
    normalized: str
    translated: str
    confidence: float
    warnings: list[str] = field(default_factory=list)
    needs_confirmation: bool = False
    audio_url: str | None = None
    tts_provider: str | None = None
    media_keys: list[str] = field(default_factory=list)
    audio_cached: bool = False


async def _run_dialect_to_mandarin(
    container,
    text: str,
    *,
    scenario: str | None,
    request_id: str,
    behavior: str | None,
    transcript_confidence: float,
    base_warnings: list[str],
) -> _DialectOutput:
    settings = container.settings
    warnings = list(base_warnings)
    needs_confirmation = False

    try:
        if behavior == "llm_error":
            raise ProviderError("llm_injected_error", "注入的语言模型错误。")
        llm = await container.llm.to_mandarin(text, scenario=scenario)
        normalized = llm.normalized_mandarin.strip() or text
        confidence = min(transcript_confidence, llm.confidence)
        needs_confirmation = llm.needs_confirmation
    except ProviderError:
        # Degrade to the transcript instead of failing the conversation.
        normalized = text
        confidence = min(transcript_confidence, 0.35)
        needs_confirmation = True
        warnings.append("llm_degraded")

    if transcript_confidence < settings.asr_hint_confidence and "low_confidence" not in warnings:
        warnings.append("low_confidence")
        needs_confirmation = True

    if _numbers_lost(text, normalized):
        # 数字、金额、药名剂量不能被静默改写（spec 9.2）：保留文字但要求确认。
        warnings.append("numbers_changed")
        needs_confirmation = True

    audio_url: str | None = None
    tts_provider: str | None = None
    media_keys: list[str] = []
    audio_cached = False
    cache_key = _build_cache_key(settings, normalized, "mandarin")
    cached_entry = container.cache.get(cache_key)
    if cached_entry and container.media.exists(cached_entry["key"]):
        audio_url = container.media.sign(cached_entry["key"])
        tts_provider = cached_entry["provider"]
        media_keys.append(cached_entry["key"])
        audio_cached = True
    else:
        result = None
        if behavior != "tts_error":
            result = await _synthesize_with_fallback(container, normalized, "mandarin", request_id)
        if result is not None:
            key = container.media.put(result.audio or b"", result.ext)
            media_keys.append(key)
            audio_url = container.media.sign(key)
            tts_provider = result.provider
            container.cache.set(cache_key, {"key": key, "provider": tts_provider})
            if result.provider == "phrase_pack":
                warnings.append("cached_phrase")
        else:
            warnings.append("tts_error")

    return _DialectOutput(
        normalized=normalized,
        translated=normalized,
        confidence=round(confidence, 3),
        warnings=warnings,
        needs_confirmation=needs_confirmation,
        audio_url=audio_url,
        tts_provider=tts_provider,
        media_keys=media_keys,
        audio_cached=audio_cached,
    )


@router.post("/translate/audio", response_model=TranslateAudioResponse)
async def translate_audio(
    request: Request,
    audio: UploadFile = File(..., description="16k mono 16-bit PCM/WAV, <=30s, <=2MB"),
    requestId: str = Form(..., min_length=6, max_length=64),
    dialectId: str = Form("lanzhou"),
    scenario: str = Form(""),
):
    started = time.perf_counter()
    container = get_container(request)
    settings = container.settings

    _validate_request_id(requestId)
    if dialectId != "lanzhou":
        raise ApiError(
            400, "unsupported_dialect", "当前只支持兰州话（试运行），其他片区将在后续版本加入。"
        )
    scenario_value = _parse_scenario(scenario)
    behavior = debug_behavior(request)
    if behavior not in _DEBUG_BEHAVIORS:
        behavior = None

    raw = await audio.read(settings.max_audio_bytes + 1)
    try:
        info = validate_audio(
            raw,
            min_seconds=settings.min_record_seconds,
            max_seconds=settings.max_record_seconds,
            max_bytes=settings.max_audio_bytes,
        )
    except AudioError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message) from exc

    idempotency_key = f"audio:{requestId}"
    lock = container.get_lock(requestId)
    async with lock:
        replay = container.idempotency.get(idempotency_key)
        if replay:
            response = TranslateAudioResponse(**replay)
            response.cached = True
            response.latencyMs = int((time.perf_counter() - started) * 1000)
            return response

        hint = None
        if container.asr.mode == "mock" and settings.enable_debug_hooks:
            hint = request.headers.get("x-mock-asr-text") or None

        try:
            asr = await container.asr.transcribe(
                info.pcm, info.sample_rate, scenario=scenario_value, hint_text=hint
            )
        except ProviderError as exc:
            raise ApiError(
                504 if exc.retryable else 502,
                exc.code,
                exc.message,
                retryable=exc.retryable,
            ) from exc

        if behavior == "asr_empty":
            asr.text = ""
            asr.confidence = 0.0
        elif behavior == "asr_low":
            asr.confidence = 0.3

        text = asr.text.strip()
        if not text:
            raise ApiError(422, "asr_empty", "没听清，再说一遍或直接改文字。", retryable=True)
        if asr.confidence < settings.asr_min_confidence:
            raise ApiError(
                422,
                "low_confidence",
                "这句可能没听清，点文字改一下。",
                retryable=True,
                details={"asrText": text, "confidence": round(asr.confidence, 2)},
            )

        output = await _run_dialect_to_mandarin(
            container,
            text,
            scenario=scenario_value,
            request_id=requestId,
            behavior=behavior,
            transcript_confidence=asr.confidence,
            base_warnings=list(asr.warnings),
        )

        response = TranslateAudioResponse(
            requestId=requestId,
            direction=Direction.dialect_to_mandarin,
            asrText=text,
            normalizedText=output.normalized,
            translatedText=output.translated,
            outputText=output.translated,
            outputAudioUrl=output.audio_url,
            confidence=output.confidence,
            cached=output.audio_cached,
            warnings=output.warnings,
            needsConfirmation=output.needs_confirmation,
            latencyMs=int((time.perf_counter() - started) * 1000),
        )
        container.idempotency.set(idempotency_key, response.model_dump(mode="json"))
        container.records.put(
            requestId,
            direction=Direction.dialect_to_mandarin.value,
            scenario=scenario_value,
            mediaKeys=output.media_keys,
            createdAt=time.time(),
        )
        return response


@router.post("/translate/dialect-text", response_model=DialectTextResponse)
async def translate_dialect_text(request: Request, body: DialectTextRequest):
    """改字: the user fixes the ASR transcript, we re-normalize and re-synthesize."""
    started = time.perf_counter()
    container = get_container(request)
    behavior = debug_behavior(request)
    if behavior not in _DEBUG_BEHAVIORS:
        behavior = None
    scenario_value = body.scenario.value if body.scenario else None

    idempotency_key = f"dialect:text:{body.requestId}"
    lock = container.get_lock(body.requestId)
    async with lock:
        replay = container.idempotency.get(idempotency_key)
        if replay:
            response = DialectTextResponse(**replay)
            response.cached = True
            response.latencyMs = int((time.perf_counter() - started) * 1000)
            return response

        output = await _run_dialect_to_mandarin(
            container,
            body.text,
            scenario=scenario_value,
            request_id=body.requestId,
            behavior=behavior,
            transcript_confidence=1.0,
            base_warnings=[],
        )
        response = DialectTextResponse(
            requestId=body.requestId,
            direction=Direction.dialect_to_mandarin,
            inputText=body.text,
            normalizedText=output.normalized,
            translatedText=output.translated,
            outputText=output.translated,
            outputAudioUrl=output.audio_url,
            ttsProvider=output.tts_provider,
            confidence=output.confidence,
            cached=output.audio_cached,
            warnings=output.warnings,
            needsConfirmation=output.needs_confirmation,
            latencyMs=int((time.perf_counter() - started) * 1000),
        )
        container.idempotency.set(idempotency_key, response.model_dump(mode="json"))
        container.records.put(
            body.requestId,
            direction=Direction.dialect_to_mandarin.value,
            scenario=scenario_value,
            mediaKeys=output.media_keys,
            createdAt=time.time(),
        )
        return response


@router.post("/translate/text", response_model=TranslateTextResponse)
async def translate_text(request: Request, body: TranslateTextRequest):
    started = time.perf_counter()
    container = get_container(request)
    settings = container.settings

    if body.direction != Direction.mandarin_to_dialect:
        raise ApiError(
            400,
            "unsupported_direction",
            "文本接口只支持 mandarin_to_dialect；兰州话转普通话请用录音或改字接口。",
        )
    scenario_value = body.scenario.value if body.scenario else None
    behavior = debug_behavior(request)
    if behavior not in _DEBUG_BEHAVIORS:
        behavior = None

    idempotency_key = f"text:{body.requestId}"
    lock = container.get_lock(body.requestId)
    async with lock:
        replay = container.idempotency.get(idempotency_key)
        if replay:
            response = TranslateTextResponse(**replay)
            response.cached = True
            response.latencyMs = int((time.perf_counter() - started) * 1000)
            warnings = list(response.warnings)
            if "idempotent_replay" not in warnings:
                warnings.append("idempotent_replay")
            response.warnings = warnings
            return response

        warnings: list[str] = []
        needs_confirmation = False
        degraded = False
        try:
            if behavior == "llm_error":
                raise ProviderError("llm_injected_error", "注入的语言模型错误。")
            llm = await container.llm.to_dialect(body.text, scenario=scenario_value)
            dialect_text = llm.dialect_text.strip() or body.text
            back_translation = llm.back_translation or body.text
            confidence = llm.confidence
            needs_confirmation = llm.needs_confirmation
        except ProviderError:
            dialect_text = body.text
            back_translation = body.text
            confidence = 0.3
            needs_confirmation = True
            degraded = True
            warnings.append("llm_degraded")

        if _numbers_lost(body.text, dialect_text):
            warnings.append("numbers_changed")
            needs_confirmation = True

        audio_url: str | None = None
        tts_provider: str | None = None
        media_keys: list[str] = []
        audio_cached = False
        cache_key = _build_cache_key(settings, dialect_text, "dialect")
        cached_entry = container.cache.get(cache_key)
        if cached_entry and container.media.exists(cached_entry["key"]):
            audio_url = container.media.sign(cached_entry["key"])
            tts_provider = cached_entry["provider"]
            media_keys.append(cached_entry["key"])
            audio_cached = True
        elif degraded:
            warnings.append("text_only")
        else:
            result = None
            if behavior != "tts_error":
                result = await _synthesize_with_fallback(
                    container, dialect_text, "dialect", body.requestId
                )
            if result is not None:
                key = container.media.put(result.audio or b"", result.ext)
                media_keys.append(key)
                audio_url = container.media.sign(key)
                tts_provider = result.provider
                container.cache.set(cache_key, {"key": key, "provider": tts_provider})
                if result.provider == "phrase_pack":
                    warnings.append("cached_phrase")
            else:
                warnings.append("tts_error")

        response = TranslateTextResponse(
            requestId=body.requestId,
            direction=Direction.mandarin_to_dialect,
            inputText=body.text,
            dialectText=dialect_text,
            backTranslation=back_translation,
            outputText=dialect_text,
            outputAudioUrl=audio_url,
            ttsProvider=tts_provider,
            confidence=round(confidence, 3),
            cached=audio_cached,
            warnings=warnings,
            needsConfirmation=needs_confirmation,
            latencyMs=int((time.perf_counter() - started) * 1000),
        )
        container.idempotency.set(idempotency_key, response.model_dump(mode="json"))
        container.records.put(
            body.requestId,
            direction=Direction.mandarin_to_dialect.value,
            scenario=scenario_value,
            mediaKeys=media_keys,
            createdAt=time.time(),
        )
        return response
