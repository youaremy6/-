"""Audio validation for 16 kHz mono 16-bit PCM input (spec 5.3 / 6.2).

The mini program records `format: 'PCM'`; depending on the base library the
temp file is either a bare PCM stream or a RIFF/WAVE container, so both are
accepted.  Anything else is rejected with 415 instead of being guessed at.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass

SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2
CHANNELS = 1

_MP3_MAGIC = (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xfa")
_CONTAINER_MAGIC = {
    b"OggS": "ogg",
    b"#!AMR": "amr",
    b"fLaC": "flac",
}


class AudioError(Exception):
    """Raised when an upload cannot be accepted as 16k mono PCM."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class AudioInfo:
    pcm: bytes
    sample_rate: int
    channels: int
    sample_width: int
    duration_s: float
    container: str


def _detect_container(data: bytes) -> str:
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    for magic, name in _CONTAINER_MAGIC.items():
        if data.startswith(magic):
            return name
    if data[:2] in _MP3_MAGIC or data[:3] == b"ID3":
        return "mp3"
    if data[4:8] == b"ftyp":
        return "mp4"
    return "pcm"


def validate_audio(
    data: bytes,
    *,
    min_seconds: float = 0.8,
    max_seconds: int = 30,
    max_bytes: int = 2_000_000,
) -> AudioInfo:
    if not data:
        raise AudioError("empty_audio", "上传的音频是空的。", status_code=400)
    if len(data) > max_bytes:
        raise AudioError(
            "audio_too_large",
            f"音频超过 {max_bytes // 1_000_000} MB 上限。",
            status_code=413,
        )

    container = _detect_container(data)
    if container == "wav":
        pcm, sample_rate, channels, sample_width = _read_wav(data)
    elif container == "pcm":
        pcm, sample_rate, channels, sample_width = data, SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH
    else:
        raise AudioError(
            "unsupported_audio",
            f"只接受 16k 单声道 PCM/WAV，收到的是 {container}。",
            status_code=415,
        )

    if sample_rate != SAMPLE_RATE or channels != CHANNELS or sample_width != SAMPLE_WIDTH:
        raise AudioError(
            "unsupported_audio",
            f"只接受 16 kHz 单声道 16-bit PCM，收到 {sample_rate} Hz / {channels} 声道 / {sample_width * 8} bit。",
            status_code=415,
        )
    if len(pcm) % SAMPLE_WIDTH:
        raise AudioError("unsupported_audio", "PCM 字节数为奇数，疑似文件被截断。", status_code=415)

    duration = len(pcm) / (sample_rate * sample_width)
    if duration < min_seconds:
        raise AudioError(
            "too_short",
            f"太短了，按住多说一会儿（至少 {min_seconds:g} 秒）。",
            status_code=422,
        )
    if duration > max_seconds:
        raise AudioError(
            "too_long",
            f"一次说一句，最多 {max_seconds} 秒。",
            status_code=422,
        )
    return AudioInfo(
        pcm=pcm,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
        duration_s=round(duration, 3),
        container=container,
    )


def _read_wav(data: bytes) -> tuple[bytes, int, int, int]:
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            if wav.getcomptype() != "NONE":
                raise AudioError("unsupported_audio", "WAV 不是未压缩 PCM。", status_code=415)
            return (
                wav.readframes(wav.getnframes()),
                wav.getframerate(),
                wav.getnchannels(),
                wav.getsampwidth(),
            )
    except AudioError:
        raise
    except (wave.Error, EOFError) as exc:
        raise AudioError("unsupported_audio", f"WAV 文件无法解析：{exc}", status_code=415) from exc


def wrap_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap header-less PCM (as returned by CosyVoice) into a playable WAV."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()
