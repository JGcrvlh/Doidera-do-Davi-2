from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- captura / OCR


class RawCapture(BaseModel):
    png: bytes
    width: int
    height: int
    window_title: str | None = None
    process_name: str | None = None
    monitor: int = 0
    captured_at: datetime = Field(default_factory=utcnow)


class OcrBlock(BaseModel):
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 em pixels
    confidence: float = 1.0


class OcrResult(BaseModel):
    blocks: list[OcrBlock] = []
    full_text: str = ""
    image_hash: str | None = None
    window_title: str | None = None


# ------------------------------------------------------------------- deteccao

QuestionKind = Literal[
    "open_text", "motivation", "experience", "behavioral", "technical",
    "salary", "availability", "multiple_choice", "other",
]


class DetectedQuestion(BaseModel):
    text: str
    kind: QuestionKind = "open_text"
    char_limit: int | None = None
    options: list[str] | None = None
    confidence: float = 1.0


class JobSignals(BaseModel):
    title_snippets: list[str] = []
    requirement_snippets: list[str] = []
    culture_snippets: list[str] = []
    raw_snippets: list[str] = []

    def is_empty(self) -> bool:
        return not (
            self.title_snippets or self.requirement_snippets
            or self.culture_snippets or self.raw_snippets
        )


class ScreenAnalysis(BaseModel):
    questions: list[DetectedQuestion] = []
    job_signals: JobSignals = JobSignals()
    platform_hint: str | None = None


# ------------------------------------------------------------ contexto da vaga

Seniority = Literal["intern", "junior", "mid", "senior", "staff", "manager", "unknown"]


class JobContext(BaseModel):
    company: str | None = None
    company_domain: str | None = None
    role_title: str | None = None
    seniority: Seniority = "unknown"
    requirements: list[str] = []
    technologies: list[str] = []
    responsibilities: list[str] = []
    job_description_summary: str | None = None
    culture_signals: list[str] = []
    source_confidence: float = 0.5
    completeness: float = 0.0

    KEY_FIELDS: ClassVar[tuple[str, ...]] = (
        "company", "role_title", "requirements", "technologies",
        "job_description_summary",
    )

    def compute_completeness(self) -> float:
        filled = 0
        for name in self.KEY_FIELDS:
            value = getattr(self, name)
            if value:
                filled += 1
        if self.seniority != "unknown":
            filled += 1
        return round(filled / (len(self.KEY_FIELDS) + 1), 2)


# ----------------------------------------------------------- pesquisa (empresa)


class SourcedClaim(BaseModel):
    claim: str
    source_url: str
    source_date: str | None = None


class CompanyProfile(BaseModel):
    name: str
    summary: str = ""
    products: list[str] = []
    tech_stack_public: list[str] = []
    values_culture: list[SourcedClaim] = []
    recent_news: list[SourcedClaim] = []
    researched_at: datetime = Field(default_factory=utcnow)
    sources: list[str] = []


# ------------------------------------------------------------------- geracao


class FitMatch(BaseModel):
    requirement: str
    profile_fact_id: str
    note: str = ""


class FitAnalysis(BaseModel):
    matched: list[FitMatch] = []
    gaps: list[str] = []
    angle: str = ""


class SuggestedAnswer(BaseModel):
    fit_analysis: FitAnalysis = FitAnalysis()
    answer: str
    rationale: str = ""
    facts_used: list[str] = []
    company_claims_used: list[str] = []
    confidence: Literal["high", "medium", "low"] = "medium"
    caveats: list[str] = []


class VerificationResult(BaseModel):
    ok: bool = True
    issues: list[str] = []
    unsupported_claims: list[str] = []


class AnswerBundle(BaseModel):
    """O que chega a UI: sugestao + resultado da verificacao + custo da rodada."""

    question: DetectedQuestion
    suggestion: SuggestedAnswer
    verification: VerificationResult
    cost_usd: float = 0.0
    generated_at: datetime = Field(default_factory=utcnow)
