from __future__ import annotations

from copilot.domain.models import JobContext, JobSignals
from copilot.llm.client import LlmClient

_SYSTEM = """Voce extrai um contexto ESTRUTURADO de vaga de emprego a partir de texto de tela (OCR)
de paginas de candidatura.

Regras:
- Extraia SOMENTE o que esta no texto. Campo ausente fica null / lista vazia. NAO invente.
- technologies: nomes normalizados em minusculas (ex.: "python", "aws").
- seniority: so preencha se o texto indicar; na duvida, "unknown".
- source_confidence: quanto do resultado veio literalmente do texto (1.0) vs. inferencia (menor)."""


class ContextExtractor:
    def __init__(self, llm: LlmClient) -> None:
        self._llm = llm

    def extract(self, redacted_screen_text: str, signals: JobSignals) -> JobContext:
        snippets = "\n".join(
            signals.title_snippets + signals.requirement_snippets + signals.culture_snippets
        )
        user = (
            "Trechos ja identificados como sinais da vaga:\n"
            f"{snippets or '(nenhum)'}\n\n"
            f"Texto completo da tela:\n{redacted_screen_text}"
        )
        context = self._llm.extract(
            system=_SYSTEM, user=user, schema=JobContext, purpose="job_context",
        )
        context.completeness = context.compute_completeness()
        return context
