"""Generate the bilingual phrase pack, its audio, and the mini-program copy.

Usage (from the repo root):

    python scripts/build_phrases.py                # refresh metadata + missing audio
    python scripts/build_phrases.py --force        # re-synthesize every placeholder
    python scripts/build_phrases.py --check        # verify assets, never writes
    python scripts/build_phrases.py --skip-audio   # text-only pack (no audio files)

Native recordings are the source of truth for real audio.  Drop files at
``assets/phrases/recordings/lanzhou/<phrase_id>.wav`` (16 kHz mono 16-bit) or
``.mp3`` and they replace the generated placeholder automatically.  Without a
recording, the Lanzhou side is a **placeholder** produced by a Mandarin voice;
it is labelled ``placeholder`` in the pack and in the UI.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHRASE_DIR = ROOT / "assets" / "phrases"
SOURCE = PHRASE_DIR / "phrases.source.json"
PACK = PHRASE_DIR / "phrases.json"
AUDIO_DIR = PHRASE_DIR / "audio"
RECORDINGS_DIR = PHRASE_DIR / "recordings"
MINI = ROOT / "miniprogram"
MINI_AUDIO = MINI / "assets" / "phrases"
MINI_DATA = MINI / "data" / "phrases.js"

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
RECORDING_SUFFIXES = (".wav", ".mp3")


def _log(message: str) -> None:
    print(message, flush=True)


async def _edge_synth(text: str, voice: str, rate: str, target: Path) -> bool:
    try:
        import edge_tts
    except ImportError:
        return False
    for attempt in range(3):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(str(target))
            if target.exists() and target.stat().st_size > 800:
                return True
        except Exception as exc:  # noqa: BLE001 - retry, then fall back to SAPI
            _log(f"  edge-tts attempt {attempt + 1} failed: {type(exc).__name__}")
        await asyncio.sleep(0.4)
    return False


def _sapi_synth(text: str, target_wav: Path) -> bool:
    """Windows SAPI fallback: real speech, robotic, no network needed."""
    script = target_wav.with_suffix(".ps1")
    escaped = text.replace("'", "''")
    script.write_text(
        "Add-Type -AssemblyName System.Speech\n"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "try { $s.SelectVoice('Microsoft Huihui Desktop') } catch {}\n"
        "$s.Rate = 0\n"
        f"$s.SetOutputToWaveFile('{target_wav.as_posix()}')\n"
        f"$s.Speak('{escaped}')\n"
        "$s.Dispose()\n",
        encoding="utf-8",
    )
    try:
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            capture_output=True,
            timeout=60,
        )
        return result.returncode == 0 and target_wav.exists() and target_wav.stat().st_size > 1000
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        script.unlink(missing_ok=True)


def _encode_mp3(wav_path: Path, mp3_path: Path) -> bool:
    try:
        import lameenc
        import wave
    except ImportError:
        return False
    try:
        with wave.open(str(wav_path), "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            rate = wav.getframerate()
            channels = wav.getnchannels()
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(32)
        encoder.set_in_sample_rate(rate)
        encoder.set_channels(channels)
        encoder.set_quality(5)
        data = encoder.encode(frames) + encoder.flush()
        mp3_path.write_bytes(data)
        return mp3_path.exists() and mp3_path.stat().st_size > 800
    except Exception:  # noqa: BLE001
        return False


def _synthesize(text: str, voice: str, rate: str, base: Path, provider: str) -> tuple[Path | None, str]:
    """Returns (audio path, kind)."""
    mp3 = base.with_suffix(".mp3")
    wav = base.with_suffix(".wav")
    if provider in {"auto", "edge"} and asyncio.run(_edge_synth(text, voice, rate, mp3)):
        return mp3, "edge-tts"
    if provider in {"auto", "sapi"} and sys.platform == "win32":
        if _sapi_synth(text, wav):
            if _encode_mp3(wav, mp3):
                wav.unlink(missing_ok=True)
                return mp3, "sapi"
            return wav, "sapi"
    return None, "none"


def _find_recording(language: str, phrase_id: str) -> Path | None:
    for suffix in RECORDING_SUFFIXES:
        candidate = RECORDINGS_DIR / language / f"{phrase_id}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _validate_recording(path: Path) -> str | None:
    """Reject recordings that would not play reliably or are too long."""
    if not path.exists():
        return "file missing"
    if path.stat().st_size < 1000:
        return "文件小于 1 KB"
    if path.suffix.lower() == ".wav":
        import wave

        try:
            with wave.open(str(path), "rb") as wav:
                if wav.getcomptype() != "NONE":
                    return "WAV 必须是未压缩 PCM"
                if wav.getframerate() != 16_000:
                    return f"采样率必须是 16000（当前 {wav.getframerate()}）"
                if wav.getnchannels() != 1:
                    return f"必须是单声道（当前 {wav.getnchannels()}）"
                if wav.getsampwidth() != 2:
                    return f"必须是 16-bit（当前 {wav.getsampwidth() * 8}-bit）"
                duration = wav.getnframes() / wav.getframerate()
                if not 0.5 <= duration <= 20:
                    return f"时长应在 0.5–20 秒（当前 {duration:.2f}）"
        except Exception as exc:  # noqa: BLE001
            return f"WAV 无法解析：{exc}"
    elif path.suffix.lower() == ".mp3":
        if path.stat().st_size < 3000:
            return "MP3 文件过小"
    else:
        return "只支持 .wav / .mp3"
    return None


def _install_recording(recording: Path, target_base: Path) -> Path:
    """Copy a native recording into the audio dir and drop the stale sibling."""
    target = target_base.with_suffix(recording.suffix.lower())
    for suffix in RECORDING_SUFFIXES:
        stale = target_base.with_suffix(suffix)
        if stale != target:
            stale.unlink(missing_ok=True)
    shutil.copy2(recording, target)
    return target


def build(voice: str, rate: str, provider: str, skip_audio: bool, force: bool = False) -> int:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    (MINI / "data").mkdir(parents=True, exist_ok=True)

    old_entries: dict[str, dict] = {}
    if PACK.exists():
        try:
            old = json.loads(PACK.read_text(encoding="utf-8"))
            old_entries = {item["id"]: item for item in old.get("phrases", [])}
        except (json.JSONDecodeError, KeyError):
            old_entries = {}

    phrases = []
    counts = {"recorded": 0, "generated": 0, "reused": 0, "missing": 0}
    for item in source["phrases"]:
        entry = dict(item)
        for language, text in (("mandarin", item["mandarin"]), ("lanzhou", item["lanzhou"])):
            rel = f"audio/{language}/{item['id']}"
            target = PHRASE_DIR / rel
            if skip_audio:
                entry[f"{language}Audio"] = {"file": None, "kind": "missing", "voice": None}
                continue
            target.parent.mkdir(parents=True, exist_ok=True)

            recording = _find_recording(language, item["id"])
            if recording is not None:
                problem = _validate_recording(recording)
                if problem:
                    raise RuntimeError(f"{recording.relative_to(ROOT)}: {problem}")
                installed = _install_recording(recording, target)
                entry[f"{language}Audio"] = {
                    "file": f"{rel}{installed.suffix}",
                    "kind": "recorded",
                    "voice": "兰州话母语者录音" if language == "lanzhou" else "普通话录音",
                }
                counts["recorded"] += 1
                _log(f"  ok {item['id']} {language} <- recording {recording.name}")
                continue

            if not force:
                previous = (old_entries.get(item["id"]) or {}).get(f"{language}Audio") or {}
                previous_file = previous.get("file")
                if (
                    previous_file
                    and (PHRASE_DIR / previous_file).exists()
                    and previous.get("kind") in {"generated", "placeholder", "recorded"}
                ):
                    entry[f"{language}Audio"] = previous
                    counts["reused"] += 1
                    continue

            path, used = _synthesize(text, voice, rate, target, provider)
            if path is None:
                entry[f"{language}Audio"] = {"file": None, "kind": "missing", "voice": None}
                counts["missing"] += 1
                _log(f"  !! {item['id']} {language}: audio missing")
                continue
            for suffix in RECORDING_SUFFIXES:
                stale = target.with_suffix(suffix)
                if stale != path:
                    stale.unlink(missing_ok=True)
            kind = "generated" if language == "mandarin" else "placeholder"
            used_voice = voice if used == "edge-tts" else "Microsoft Huihui Desktop"
            if language == "lanzhou":
                used_voice = f"{used_voice}（占位，非母语者朗读）"
            entry[f"{language}Audio"] = {
                "file": f"{rel}{path.suffix}",
                "kind": kind,
                "voice": used_voice,
            }
            counts["generated"] += 1
            _log(f"  ok {item['id']} {language} <- {used}")
        phrases.append(entry)

    lanzhou_recorded = sum(
        1 for phrase in phrases if (phrase.get("lanzhouAudio") or {}).get("kind") == "recorded"
    )
    lanzhou_placeholder = sum(
        1 for phrase in phrases if (phrase.get("lanzhouAudio") or {}).get("kind") == "placeholder"
    )
    if lanzhou_placeholder:
        audio_notice = (
            f"兰州话语音 {lanzhou_recorded} 条为母语者录音，仍有 {lanzhou_placeholder} 条占位"
            "（普通话音色朗读），不得作为正式方言语音包。"
        )
    else:
        audio_notice = "兰州话语音已全部替换为母语者录音。"

    pack = {
        "version": source["version"],
        "dialectId": "lanzhou",
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator": "scripts/build_phrases.py",
        "notice": source["notice"],
        "reviewPolicy": source["reviewPolicy"],
        "audioNotice": audio_notice,
        "phrases": phrases,
    }
    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _log(
        f"wrote {PACK.relative_to(ROOT)} ({len(phrases)} phrases; "
        f"recorded={counts['recorded']} generated={counts['generated']} "
        f"reused={counts['reused']} missing={counts['missing']})"
    )

    if skip_audio:
        return 0

    # Mirror assets into the mini program package for offline playback.
    dest_audio = MINI_AUDIO / "audio"
    if dest_audio.exists():
        shutil.rmtree(dest_audio)
    shutil.copytree(AUDIO_DIR, dest_audio)

    js = (
        "// AUTO-GENERATED by scripts/build_phrases.py — do not edit by hand.\n"
        "// 兰州话文本均为 draft，必须经母语者校对后才能作为正式内容。\n"
        "module.exports = "
        + json.dumps(pack, ensure_ascii=False, indent=2)
        + ";\n"
    )
    MINI_DATA.write_text(js, encoding="utf-8")
    _log(f"wrote {MINI_DATA.relative_to(ROOT)} and {MINI_AUDIO.relative_to(ROOT)}/audio")

    notice = (
        "# 语音包状态\n\n"
        f"- 兰州话：{lanzhou_recorded} 条母语者录音，{lanzhou_placeholder} 条占位。\n"
        "- `audio/mandarin/`：本地 TTS 合成或普通话录音，仅作演示示例。\n"
        "- 占位音频由普通话音色朗读兰州话文本生成，**不是**兰州话母语者录音。\n"
        "- 替换方式：把母语者录音放到 `recordings/lanzhou/<phrase_id>.wav`（16 kHz 单声道 16-bit）"
        "或 `.mp3`，再运行 `python scripts/build_phrases.py`。\n"
        "- 发布前还需由母语者校对文本，并把 `phrases.source.json` 的 `reviewStatus` 改为 `verified`。\n"
    )
    (PHRASE_DIR / "AUDIO_NOTICE.md").write_text(notice, encoding="utf-8")
    return 0


def check() -> int:
    problems: list[str] = []
    hard: list[str] = []
    try:
        pack = json.loads(PACK.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        _log(f"FAIL: cannot read {PACK}: {exc}")
        return 1
    for phrase in pack.get("phrases", []):
        for language in ("mandarin", "lanzhou"):
            meta = phrase.get(f"{language}Audio") or {}
            if not meta.get("file"):
                problems.append(f"{phrase['id']}:{language}: no audio")
                hard.append(f"{phrase['id']}:{language}: no audio")
                continue
            path = PHRASE_DIR / meta["file"]
            if not path.exists():
                problems.append(f"{phrase['id']}:{language}: missing file {meta['file']}")
                hard.append(f"{phrase['id']}:{language}: missing file {meta['file']}")
            if meta.get("kind") == "placeholder":
                problems.append(
                    f"{phrase['id']}:{language}: placeholder audio (must be re-recorded)"
                )
        if phrase.get("reviewStatus") != "verified":
            problems.append(f"{phrase['id']}: reviewStatus={phrase.get('reviewStatus')} (draft)")

    for language in ("mandarin", "lanzhou"):
        folder = RECORDINGS_DIR / language
        if not folder.exists():
            continue
        for recording in sorted(folder.iterdir()):
            if recording.suffix.lower() not in RECORDING_SUFFIXES:
                continue
            problem = _validate_recording(recording)
            if problem:
                problems.append(f"recording {language}/{recording.name}: {problem}")
                hard.append(f"recording {language}/{recording.name}: {problem}")

    for line in problems:
        _log(f"WARN {line}")
    _log(f"phrases={len(pack.get('phrases', []))} problems={len(problems)} hard={len(hard)}")
    return 1 if hard else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the bilingual phrase pack")
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--rate", default="+0%")
    parser.add_argument("--provider", choices=["auto", "edge", "sapi", "none"], default="auto")
    parser.add_argument("--skip-audio", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-synthesize placeholder audio even if files already exist",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        return check()
    try:
        return build(args.voice, args.rate, args.provider, args.skip_audio, force=args.force)
    except RuntimeError as exc:
        _log(f"BUILD FAILED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
