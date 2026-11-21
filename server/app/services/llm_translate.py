"""OpenAI-compatible chat client for the dialect rewrite step.

Only JSON is accepted.  The prompt forbids inventing dialect words and forbids
medical/legal advice; numbers, names, amounts, drug names and units must be
preserved verbatim.  A single retry with a stricter instruction is allowed
before the API degrades to the raw text.
"""

from __future__ import annotations

import json
import re

import httpx

from ..config import Settings
from ..models.schemas import Scenario
from . import lexicon
from .base import DialectResult, MandarinResult, ProviderError

_SCENARIO_LABEL = {
    Scenario.medical: "就医",
    Scenario.transport: "出行",
    Scenario.market: "买卖",
    Scenario.help: "求助",
}

_MANDARIN_SYSTEM = """你是兰州话（兰银官话金城片）口语转写助手，当前场景：{scenario}。
任务：把用户给出的兰州话口语转写成通顺、忠实的普通话。
规则：
1. 只做语言规范化；不解释、不扩写、不添加原文没有的信息。
2. 人名、地名、数字、金额、药名、单位必须原样保留，不得改写或换算。
3. 不做医疗诊断、法律或金融建议，只做语言转写。
4. 不确定的词不要猜：降低 meaningConfidence，并把原词写进 uncertainWords。
5. 方言用词只能来自原文或下面的词表，不得凭空创造。
6. 只输出一个 JSON 对象（不要 Markdown 代码块），字段：
   normalizedMandarin (string), meaningConfidence (0-1 number),
   uncertainWords (string array), needsConfirmation (boolean)。

可用词表（兰州话 -> 普通话）：
{glossary}
"""

_DIALECT_SYSTEM = """你是兰州话（兰银官话金城片）口语改写助手，当前场景：{scenario}。
任务：把用户给出的普通话改写成兰州人日常会说的兰州话，并给出回译供用户核对。
规则：
1. 只改写表达方式，不增加、不删减事实；数字、金额、药名、地址、人名必须原样保留。
2. 方言词只能来自下面的词表或已存在的原文词语，不得凭空造词；没有把握就用接近普通话的说法。
3. 回译 backTranslation 必须是你这句方言对应的普通话意思，不是复述原文。
4. 不做医疗诊断、法律或金融建议。
5. 不确定时降低 meaningConfidence 并写入 uncertainWords。
6. 只输出一个 JSON 对象（不要 Markdown 代码块），字段：
   dialectText (string), backTranslation (string), meaningConfidence (0-1 number),
   uncertainWords (string array), needsConfirmation (boolean)。

可用词表（普通话 -> 兰州话）：
{glossary}
"""


def _glossary(pairs: list[tuple[str, str]]) -> str:
    return "、".join(f"{src}→{dst}" for src, dst in pairs)


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ProviderError("llm_invalid_output", "LLM 没有返回 JSON 对象。", retryable=False)
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ProviderError("llm_invalid_output", f"LLM 返回的 JSON 无法解析：{exc}", retryable=False) from exc
    if not isinstance(payload, dict):
        raise ProviderError("llm_invalid_output", "LLM 返回值不是 JSON 对象。", retryable=False)
    return payload


def _confidence(value: object, default: float = 0.6) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


class OpenAICompatibleLLM:
    name = "llm"
    mode = "live"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.llm_base_url.rstrip("/")

    async def _chat(self, system: str, user: str) -> dict:
        url = f"{self._base}/chat/completions"
        payload = {
            "model": self._settings.llm_model,
            "temperature": self._settings.llm_temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._settings.llm_api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 400:
                    # Some compatible gateways reject response_format.
                    payload.pop("response_format", None)
                    response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderError("llm_timeout", "语言模型超时。") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("llm_upstream_error", f"语言模型请求失败：{exc}") from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("llm_invalid_output", "语言模型响应缺少内容。") from exc
        return _extract_json(content if isinstance(content, str) else str(content))

    async def to_mandarin(self, text: str, *, scenario: str | None = None) -> MandarinResult:
        label = _SCENARIO_LABEL.get(Scenario(scenario), "未指定") if scenario else "未指定"
        system = _MANDARIN_SYSTEM.format(scenario=label, glossary=_glossary(lexicon.LANZHOU_TO_MANDARIN))
        payload = await self._chat(system, f"兰州话原话：{text}")
        translated = str(payload.get("normalizedMandarin", "")).strip()
        if not translated:
            raise ProviderError("llm_invalid_output", "LLM 未给出 normalizedMandarin。", retryable=False)
        confidence = _confidence(payload.get("meaningConfidence"), 0.7)
        uncertain = [str(item) for item in payload.get("uncertainWords") or []][:8]
        return MandarinResult(
            normalized_mandarin=translated,
            confidence=confidence,
            uncertain_words=uncertain,
            needs_confirmation=bool(payload.get("needsConfirmation")) or confidence < 0.7,
        )

    async def to_dialect(self, text: str, *, scenario: str | None = None) -> DialectResult:
        label = _SCENARIO_LABEL.get(Scenario(scenario), "未指定") if scenario else "未指定"
        system = _DIALECT_SYSTEM.format(scenario=label, glossary=_glossary(lexicon.MANDARIN_TO_LANZHOU))
        payload = await self._chat(system, f"普通话：{text}")
        dialect = str(payload.get("dialectText", "")).strip()
        back = str(payload.get("backTranslation", "")).strip()
        if not dialect:
            raise ProviderError("llm_invalid_output", "LLM 未给出 dialectText。", retryable=False)
        confidence = _confidence(payload.get("meaningConfidence"), 0.7)
        uncertain = [str(item) for item in payload.get("uncertainWords") or []][:8]
        return DialectResult(
            dialect_text=dialect,
            back_translation=back or text,
            confidence=confidence,
            uncertain_words=uncertain,
            needs_confirmation=bool(payload.get("needsConfirmation")) or confidence < 0.7,
        )
