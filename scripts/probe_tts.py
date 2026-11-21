"""Probe B: synthesize 10 Mandarin sentences with CosyVoice3 in Lanzhou style.

Requirements (spec 3B):
  - a written-consent Lanzhou native speaker reference audio (<=30 s, quiet)
  - COSYVOICE_BASE_URL + COSYVOICE_PROMPT_AUDIO_URL configured
  - GPU service reachable

Usage:
    python scripts/probe_tts.py
    python scripts/probe_tts.py --texts my_sentences.txt --out eval/lanzhou/tts_probe

The script writes audio files and prints their paths.  Intelligibility /
authenticity scores are human judgements (3 listeners, 1-5) that belong in
docs/spikes.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from app.config import get_settings  # noqa: E402
from app.services.tts_cosyvoice import CosyVoiceTTS  # noqa: E402

DEFAULT_TEXTS = [
    "医生，我有点头晕。",
    "这个药一天吃三次。",
    "请问挂号处在哪儿？",
    "到火车站大概要多久？",
    "师傅，前面路口停一下。",
    "这个多少钱一斤？",
    "能便宜一点吗？",
    "可以微信支付吗？",
    "我赶时间，麻烦快一点。",
    "我的行李还在后备箱里。",
]


async def run(texts: list[str], out_dir: Path) -> int:
    settings = get_settings()
    if not settings.tts_live_ready():
        print("SKIPPED: CosyVoice3 未配置。")
        print("需要 COSYVOICE_BASE_URL 与 COSYVOICE_PROMPT_AUDIO_URL（母语者书面同意的参考音频）。")
        return 2

    provider = CosyVoiceTTS(settings)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, text in enumerate(texts, start=1):
        try:
            result = await provider.synthesize(text, mode="dialect", request_id=f"probe_tts_{index:02d}")
        except Exception as exc:  # noqa: BLE001
            print(f"{index:02d}: ERROR {type(exc).__name__}: {exc}")
            manifest.append({"index": index, "text": text, "error": type(exc).__name__})
            continue
        target = out_dir / f"probe_{index:02d}{result.ext}"
        target.write_bytes(result.audio or b"")
        print(f"{index:02d}: {target} ({len(result.audio or b'')} bytes)")
        manifest.append({"index": index, "text": text, "file": str(target), "provider": result.provider})

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("人工评分：3 位听者分别给“能否听懂”“像不像兰州话”打 1-5 分，记录到 docs/spikes.md。")
    print("低于 可懂度 4/5 或 像不像 3/5，就必须只保留文字 + 预设语音包，不宣称实时甘肃话 TTS。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe B: CosyVoice3 兰州话合成")
    parser.add_argument("--texts", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "lanzhou" / "tts_probe")
    args = parser.parse_args()

    texts = DEFAULT_TEXTS
    if args.texts and args.texts.exists():
        texts = [line.strip() for line in args.texts.read_text(encoding="utf-8").splitlines() if line.strip()]
    return asyncio.run(run(texts, args.out))


if __name__ == "__main__":
    raise SystemExit(main())
