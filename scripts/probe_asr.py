"""Probe A: send real Lanzhou PCM recordings to 讯飞 甘肃话 ASR.

Requirements (spec 3A):
  - 15-30 s of 16 kHz mono 16-bit PCM per sample
  - XF_APP_ID / XF_API_KEY / XF_API_SECRET / XF_ACCENT_GANSU configured
  - the Gansu accent token read from the 讯飞 console (never guessed)

Usage:
    python scripts/probe_asr.py sample1.pcm sample2.wav sample3.pcm
    python scripts/probe_asr.py --out eval/lanzhou/probe_asr_results.json samples/*.pcm

The script only prints machine results; the "can a human understand the
meaning" score is a human judgement that belongs in docs/spikes.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from app.config import get_settings  # noqa: E402
from app.services.asr_xfyun import XfyunASR  # noqa: E402
from app.utils.audio import AudioError, validate_audio  # noqa: E402


async def run(paths: list[Path], out: Path | None) -> int:
    settings = get_settings()
    if not settings.asr_live_ready():
        print("SKIPPED: 讯飞 ASR 凭据不完整。")
        print("需要设置 XF_APP_ID / XF_API_KEY / XF_API_SECRET / XF_ACCENT_GANSU。")
        print("XF_ACCENT_GANSU 必须从讯飞控制台读取，禁止猜测。")
        return 2

    provider = XfyunASR(settings)
    results = []
    for path in paths:
        data = path.read_bytes()
        try:
            info = validate_audio(data, min_seconds=1.0, max_seconds=30)
        except AudioError as exc:
            print(f"{path.name}: invalid audio ({exc.code}: {exc.message})")
            results.append({"file": path.name, "error": exc.code})
            continue
        started = time.perf_counter()
        try:
            asr = await provider.transcribe(info.pcm, info.sample_rate)
            elapsed = int((time.perf_counter() - started) * 1000)
            print(f"{path.name}: {asr.text!r} ({elapsed} ms)")
            results.append(
                {
                    "file": path.name,
                    "duration_s": info.duration_s,
                    "text": asr.text,
                    "empty": not bool(asr.text.strip()),
                    "latency_ms": elapsed,
                    "provider": asr.provider,
                }
            )
        except Exception as exc:  # noqa: BLE001 - probe reports, never crashes silently
            elapsed = int((time.perf_counter() - started) * 1000)
            print(f"{path.name}: ERROR {type(exc).__name__}: {exc} ({elapsed} ms)")
            results.append({"file": path.name, "error": type(exc).__name__, "latency_ms": elapsed})

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {out}")
    print("人工评分：把每段转写交给 3 位听者判断“能否读懂原意”，记录到 docs/spikes.md。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe A: 讯飞 甘肃话 ASR")
    parser.add_argument("samples", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    return asyncio.run(run(args.samples, args.out))


if __name__ == "__main__":
    raise SystemExit(main())
