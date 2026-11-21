"""Character Error Rate (CER) and score merge for the Lanzhou evaluation set.

Usage:
    # 1) after transcribing audio/*.pcm with the ASR provider, produce:
    #    hypothesis.csv  with columns: item_id,text
    python eval/lanzhou/run_eval.py --hypothesis hypothesis.csv
    # 2) optional human scores:
    #    scores.csv with columns: item_id,meaning_score,tts_intelligibility,tts_authenticity
    python eval/lanzhou/run_eval.py --hypothesis hypothesis.csv --scores scores.csv

The default run (no hypothesis) writes results.csv with empty CER and prints
"not_run" — it never invents numbers.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUNCTUATION = set("，。！？、；：“”‘’（）《》…—,.!?;:\"'()<> \t\n")


def normalize(text: str) -> str:
    return "".join(char for char in (text or "") if char not in PUNCTUATION).strip().lower()


def edit_distance(ref: str, hyp: str) -> int:
    if not ref:
        return len(hyp)
    if not hyp:
        return len(ref)
    previous = list(range(len(hyp) + 1))
    for i, ref_char in enumerate(ref, start=1):
        current = [i]
        for j, hyp_char in enumerate(hyp, start=1):
            cost = 0 if ref_char == hyp_char else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def cer(ref: str, hyp: str) -> float:
    ref_normalized = normalize(ref)
    if not ref_normalized:
        return 0.0 if not normalize(hyp) else 1.0
    return edit_distance(ref_normalized, normalize(hyp)) / len(ref_normalized)


def read_csv(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_results(rows: list[dict], out: Path) -> None:
    fields = [
        "item_id",
        "speaker",
        "scene",
        "ref_text",
        "hypothesis",
        "cer",
        "meaning_score",
        "tts_intelligibility",
        "tts_authenticity",
        "notes",
    ]
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Lanzhou evaluation: CER + score merge")
    parser.add_argument("--metadata", type=Path, default=HERE / "metadata.csv")
    parser.add_argument("--hypothesis", type=Path, default=None)
    parser.add_argument("--scores", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=HERE / "results.csv")
    args = parser.parse_args()

    metadata = read_csv(args.metadata)
    if not metadata:
        print(f"metadata not found or empty: {args.metadata}")
        return 1

    hypotheses = {row["item_id"]: row.get("text", "") for row in read_csv(args.hypothesis)}
    scores = {
        row["item_id"]: row
        for row in read_csv(args.scores)
        if row.get("item_id")
    }

    rows = []
    cer_values = []
    for item in metadata:
        item_id = item["item_id"]
        hypothesis = hypotheses.get(item_id, "")
        value = "" if not hypotheses else f"{cer(item.get('ref_text', ''), hypothesis):.4f}"
        if value:
            cer_values.append(float(value))
        score = scores.get(item_id, {})
        rows.append(
            {
                "item_id": item_id,
                "speaker": item.get("speaker", ""),
                "scene": item.get("scene", ""),
                "ref_text": item.get("ref_text", ""),
                "hypothesis": hypothesis,
                "cer": value,
                "meaning_score": score.get("meaning_score", ""),
                "tts_intelligibility": score.get("tts_intelligibility", ""),
                "tts_authenticity": score.get("tts_authenticity", ""),
                "notes": item.get("status", ""),
            }
        )

    write_results(rows, args.out)
    if not hypotheses:
        print(f"not_run: metadata={len(rows)} items, no hypothesis.csv supplied")
        print(f"wrote template {args.out}; CER columns are empty on purpose")
        return 0

    mean_cer = sum(cer_values) / len(cer_values) if cer_values else 0.0
    print(f"items={len(rows)} transcribed={len(cer_values)} mean_CER={mean_cer:.4f}")
    print(f"wrote {args.out}")
    if mean_cer >= 0.30:
        print("WARN: mean CER >= 30%，未达到验收标准 9.2；按 spec 降级。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
