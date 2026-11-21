"""讯飞流式听写 (IAT) client for Lanzhou-accent speech.

Auth, signature and frame layout follow the public IAT WebSocket protocol.
The Gansu accent token is *not* guessed: it must come from
``XF_ACCENT_GANSU`` after the dialect service is enabled in the 讯飞 console.
Without it the live provider stays disabled and /health reports it.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from email.utils import formatdate
from urllib.parse import urlencode, urlparse

from ..config import Settings
from .base import ASRResult, ProviderError

_FRAME_BYTES = 1280  # 40 ms of 16 kHz / 16-bit mono


class XfyunASR:
    name = "xfyun"
    mode = "live"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._url = settings.xf_asr_url
        self._accent = settings.xf_accent_gansu
        self._domain = settings.xf_domain

    def _signed_url(self) -> str:
        parsed = urlparse(self._url)
        host = parsed.netloc
        path = parsed.path or "/v2/iat"
        date = formatdate(timeval=None, localtime=False, usegmt=True)
        signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
        signature = base64.b64encode(
            hmac.new(
                self._settings.xf_api_secret.encode("utf-8"),
                signature_origin.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        authorization_origin = (
            f'api_key="{self._settings.xf_api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'
        )
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
        query = urlencode({"authorization": authorization, "date": date, "host": host})
        return f"{parsed.scheme}://{host}{path}?{query}"

    def _business(self) -> dict:
        business = {
            "language": "zh_cn",
            "domain": self._domain,
            "accent": self._accent,
            "eos": 5000,
        }
        # 动态修正 dwa 只对中文普通话生效；方言/免切模式下不要带。
        if self._domain == "iat" and self._accent in {"", "mandarin"}:
            business["dwa"] = "wpgs"
        return business

    async def transcribe(
        self,
        pcm: bytes,
        sample_rate: int,
        *,
        scenario: str | None = None,
        hint_text: str | None = None,
    ) -> ASRResult:
        import websockets

        if sample_rate != 16_000:
            raise ProviderError("asr_unsupported_audio", "讯飞听写只接受 16k PCM。", retryable=False)
        if not self._settings.asr_live_ready():
            raise ProviderError("asr_not_configured", "讯飞 ASR 凭据不完整。", retryable=False)

        url = self._signed_url()
        frames = [pcm[i : i + _FRAME_BYTES] for i in range(0, len(pcm), _FRAME_BYTES)]
        try:
            texts = await asyncio.wait_for(
                self._stream(url, frames), timeout=self._settings.xf_asr_timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            raise ProviderError("asr_timeout", "讯飞听写超时。") from exc
        except ProviderError:
            raise
        except Exception as exc:  # websocket / network errors
            raise ProviderError("asr_network_error", f"讯飞听写连接失败：{exc}") from exc

        text = "".join(texts).strip()
        return ASRResult(text=text, confidence=0.9 if text else 0.0, provider=self.name)

    async def _stream(self, url: str, frames: list[bytes]) -> list[str]:
        import websockets

        segments: dict[int, str] = {}
        async with websockets.connect(url, max_size=8 * 1024 * 1024) as ws:
            first = {
                "common": {"app_id": self._settings.xf_app_id},
                "business": self._business(),
                "data": {
                    "status": 0,
                    "format": "audio/L16;rate=16000",
                    "encoding": "raw",
                    "audio": base64.b64encode(frames[0] if frames else b"").decode("utf-8"),
                },
            }
            await ws.send(json.dumps(first))
            for chunk in frames[1:]:
                await ws.send(
                    json.dumps(
                        {
                            "data": {
                                "status": 1,
                                "format": "audio/L16;rate=16000",
                                "encoding": "raw",
                                "audio": base64.b64encode(chunk).decode("utf-8"),
                            }
                        }
                    )
                )
            await ws.send(
                json.dumps(
                    {"data": {"status": 2, "format": "audio/L16;rate=16000", "encoding": "raw", "audio": ""}}
                )
            )

            while True:
                raw = await ws.recv()
                message = json.loads(raw)
                code = message.get("code", 0)
                if code != 0:
                    raise ProviderError(
                        f"asr_upstream_{code}", message.get("message", "讯飞听写返回错误。")
                    )
                data = message.get("data") or {}
                result = data.get("result") or {}
                if result.get("pgs") == "rpl" and result.get("rg"):
                    start, end = result["rg"][0], result["rg"][1]
                    for index in [k for k in segments if start - 1 <= k <= end - 1]:
                        segments.pop(index, None)
                ws_list = result.get("ws") or []
                piece = "".join(
                    word.get("w", "") for item in ws_list for word in (item.get("cw") or [])
                )
                if piece:
                    segments[int(result.get("sn", len(segments)))] = piece
                if data.get("status") == 2:
                    break
        return [segments[k] for k in sorted(segments)]
