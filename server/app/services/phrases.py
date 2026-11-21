"""Preset phrase pack: bilingual texts plus bundled audio (spec 4.1.2 / 6.2).

The JSON pack on disk is the single source of truth.  The mini program ships a
generated copy of the same data so phrases stay usable when offline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..models.schemas import Phrase, PhraseAudio, PhraseListResponse, Scenario

_NOTICE = "预设句为草稿文本，需经兰州话母语者校对后才能作为正式内容发布。"


@dataclass(frozen=True)
class PhraseRecord:
    id: str
    scenario: str
    mandarin: str
    lanzhou: str
    review_status: str
    note: str | None
    mandarin_audio: dict | None
    lanzhou_audio: dict | None


class PhraseRepository:
    def __init__(self, pack_path: Path, asset_dir: Path, public_base_url: str) -> None:
        self.pack_path = Path(pack_path)
        self.asset_dir = Path(asset_dir)
        self.public_base_url = public_base_url.rstrip("/")
        self._phrases: list[PhraseRecord] = []
        self._by_id: dict[str, PhraseRecord] = {}
        self._pack_meta: dict = {}
        self.load_error: str | None = None
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.pack_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.load_error = f"phrase pack missing: {self.pack_path}"
            self._phrases = []
            self._by_id = {}
            return
        except json.JSONDecodeError as exc:
            self.load_error = f"phrase pack is not valid JSON: {exc}"
            self._phrases = []
            self._by_id = {}
            return

        self._pack_meta = {k: v for k, v in raw.items() if k != "phrases"}
        records: list[PhraseRecord] = []
        for item in raw.get("phrases", []):
            record = PhraseRecord(
                id=str(item["id"]),
                scenario=str(item["scenario"]),
                mandarin=str(item["mandarin"]),
                lanzhou=str(item["lanzhou"]),
                review_status=str(item.get("reviewStatus", "draft")),
                note=item.get("note"),
                mandarin_audio=item.get("mandarinAudio"),
                lanzhou_audio=item.get("lanzhouAudio"),
            )
            records.append(record)
        self._phrases = records
        self._by_id = {p.id: p for p in records}
        self.load_error = None

    # -- queries ---------------------------------------------------------
    @property
    def loaded(self) -> bool:
        return self.load_error is None

    @property
    def version(self) -> str:
        return str(self._pack_meta.get("version", "unknown"))

    @property
    def generated_at(self) -> str:
        return str(self._pack_meta.get("generatedAt", ""))

    def all(self) -> list[PhraseRecord]:
        return list(self._phrases)

    def list(self, scenario: str | None = None) -> list[PhraseRecord]:
        if scenario is None:
            return list(self._phrases)
        return [p for p in self._phrases if p.scenario == scenario]

    def get(self, phrase_id: str) -> PhraseRecord | None:
        return self._by_id.get(phrase_id)

    def find_by_text(self, text: str, language: str = "lanzhou") -> PhraseRecord | None:
        needle = _normalize(text)
        field = "lanzhou" if language == "lanzhou" else "mandarin"
        for phrase in self._phrases:
            if _normalize(getattr(phrase, field)) == needle:
                return phrase
        return None

    def audio_path(self, phrase: PhraseRecord, language: str) -> Path | None:
        meta = phrase.lanzhou_audio if language == "lanzhou" else phrase.mandarin_audio
        if not meta or not meta.get("file"):
            return None
        candidate = (self.asset_dir / meta["file"]).resolve()
        try:
            candidate.relative_to(self.asset_dir.resolve())
        except ValueError:
            return None
        return candidate if candidate.exists() else None

    def audio_bytes(self, phrase: PhraseRecord, language: str) -> bytes | None:
        path = self.audio_path(phrase, language)
        return path.read_bytes() if path else None

    def audio_url(self, phrase: PhraseRecord, language: str) -> str | None:
        meta = phrase.lanzhou_audio if language == "lanzhou" else phrase.mandarin_audio
        if not meta or not meta.get("file"):
            return None
        return f"{self.public_base_url}/assets/phrases/{meta['file']}"

    # -- API shaping -----------------------------------------------------
    def to_api(self, phrase: PhraseRecord) -> Phrase:
        def audio(meta: dict | None, language: str) -> PhraseAudio:
            if not meta or not meta.get("file"):
                return PhraseAudio(kind="missing")
            return PhraseAudio(
                url=self.audio_url(phrase, language),
                kind=str(meta.get("kind", "generated")),
                voice=meta.get("voice"),
            )

        return Phrase(
            id=phrase.id,
            scenario=Scenario(phrase.scenario),
            mandarin=phrase.mandarin,
            lanzhou=phrase.lanzhou,
            reviewStatus=phrase.review_status,
            note=phrase.note,
            mandarinAudio=audio(phrase.mandarin_audio, "mandarin"),
            lanzhouAudio=audio(phrase.lanzhou_audio, "lanzhou"),
        )

    def to_api_list(self, scenario: str | None = None) -> PhraseListResponse:
        items = self.list(scenario)
        drafts = sum(1 for p in items if p.review_status != "verified")
        return PhraseListResponse(
            dialectId="lanzhou",
            count=len(items),
            draftCount=drafts,
            notice=_NOTICE,
            reviewPolicy="兰州话文本只有经过母语者校对并标记 verified 后才能作为正式内容；draft 仅作草稿展示。",
            phrases=[self.to_api(p) for p in items],
        )


def _normalize(text: str) -> str:
    table = {ord(c): None for c in "，。！？、；：“”‘’（）《》…—,.!?;:\"'()<> \t\n"}
    return text.translate(table).strip().lower()
