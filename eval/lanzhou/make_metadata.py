"""Build eval/lanzhou/metadata.csv from the phrase pack (3 speakers x 10 items).

The evaluation set itself still has to be recorded by real speakers; this
script only produces the plan/metadata scaffold with reference texts so the
collection and scoring steps are unambiguous.

Usage: python eval/lanzhou/make_metadata.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PACK = json.loads((ROOT / "assets" / "phrases" / "phrases.json").read_text(encoding="utf-8"))

# 4 就医 + 3 出行 + 3 买卖 = 10 sentences per speaker, 3 speakers = 30 items.
SELECTION = [
    "medical_01",
    "medical_02",
    "medical_04",
    "medical_06",
    "transport_01",
    "transport_03",
    "transport_05",
    "market_01",
    "market_02",
    "market_04",
]

SPEAKERS = [
    ("S1", "todo", "todo"),
    ("S2", "todo", "todo"),
    ("S3", "todo", "todo"),
]


def main() -> None:
    by_id = {phrase["id"]: phrase for phrase in PACK["phrases"]}
    rows = []
    for speaker, age_band, gender in SPEAKERS:
        for phrase_id in SELECTION:
            phrase = by_id[phrase_id]
            rows.append(
                {
                    "item_id": f"{speaker}_{phrase_id}",
                    "speaker": speaker,
                    "age_band": age_band,
                    "gender": gender,
                    "scene": phrase["scenario"],
                    "ref_text": phrase["lanzhou"],
                    "mandarin_ref": phrase["mandarin"],
                    "audio_path": f"audio/{speaker}/{phrase_id}.pcm",
                    "duration_s": "",
                    "status": "pending_recording",
                    "consent": "pending",
                }
            )

    out = HERE / "metadata.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out} ({len(rows)} items, {len(SPEAKERS)} speakers)")


if __name__ == "__main__":
    main()
