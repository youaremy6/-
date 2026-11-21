"""Wire models shared by the API and the mini program."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

REQUEST_ID_PATTERN = r"^[A-Za-z0-9_-]{6,64}$"


class Direction(str, Enum):
    dialect_to_mandarin = "dialect_to_mandarin"
    mandarin_to_dialect = "mandarin_to_dialect"


class Scenario(str, Enum):
    medical = "medical"
    transport = "transport"
    market = "market"
    help = "help"


class ReviewStatus(str, Enum):
    verified = "verified"
    draft = "draft"


class TranslateAudioResponse(BaseModel):
    requestId: str
    direction: Direction = Direction.dialect_to_mandarin
    asrText: str
    normalizedText: str
    translatedText: str
    outputText: str
    outputAudioUrl: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    cached: bool = False
    warnings: list[str] = Field(default_factory=list)
    needsConfirmation: bool = False
    latencyMs: int = 0


class TranslateTextRequest(BaseModel):
    requestId: str = Field(pattern=REQUEST_ID_PATTERN)
    direction: Direction = Direction.mandarin_to_dialect
    dialectId: str = "lanzhou"
    scenario: Scenario | None = None
    text: str = Field(min_length=1, max_length=200)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value

    @field_validator("dialectId")
    @classmethod
    def _dialect(cls, value: str) -> str:
        if value != "lanzhou":
            raise ValueError("P0 only supports dialectId=lanzhou")
        return value


class TranslateTextResponse(BaseModel):
    requestId: str
    direction: Direction = Direction.mandarin_to_dialect
    inputText: str
    dialectText: str
    backTranslation: str
    outputText: str
    outputAudioUrl: str | None = None
    ttsProvider: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    cached: bool = False
    warnings: list[str] = Field(default_factory=list)
    needsConfirmation: bool = False
    latencyMs: int = 0


class DialectTextRequest(BaseModel):
    """Used by the mini program's 改字 flow: corrected Lanzhou transcript -> Mandarin."""

    requestId: str = Field(pattern=REQUEST_ID_PATTERN)
    dialectId: str = "lanzhou"
    scenario: Scenario | None = None
    text: str = Field(min_length=1, max_length=200)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value

    @field_validator("dialectId")
    @classmethod
    def _dialect(cls, value: str) -> str:
        if value != "lanzhou":
            raise ValueError("P0 only supports dialectId=lanzhou")
        return value


class DialectTextResponse(BaseModel):
    requestId: str
    direction: Direction = Direction.dialect_to_mandarin
    inputText: str
    normalizedText: str
    translatedText: str
    outputText: str
    outputAudioUrl: str | None = None
    ttsProvider: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    cached: bool = False
    warnings: list[str] = Field(default_factory=list)
    needsConfirmation: bool = False
    latencyMs: int = 0


class PhraseAudio(BaseModel):
    url: str | None = None
    kind: str = "missing"  # generated | placeholder | missing
    voice: str | None = None


class Phrase(BaseModel):
    id: str
    scenario: Scenario
    mandarin: str
    lanzhou: str
    reviewStatus: ReviewStatus = ReviewStatus.draft
    note: str | None = None
    mandarinAudio: PhraseAudio = Field(default_factory=PhraseAudio)
    lanzhouAudio: PhraseAudio = Field(default_factory=PhraseAudio)


class PhraseListResponse(BaseModel):
    dialectId: str = "lanzhou"
    count: int
    draftCount: int
    notice: str
    reviewPolicy: str
    phrases: list[Phrase]


class HealthDependency(BaseModel):
    ok: bool
    provider: str
    mode: str  # live | mock | misconfigured
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str
    dialect: str
    dependencies: dict[str, HealthDependency]
    limits: dict[str, object]
    privacy: str


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, object] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody
