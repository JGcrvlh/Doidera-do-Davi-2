from __future__ import annotations

from copilot.domain.models import (
    CompanyProfile,
    DetectedQuestion,
    JobContext,
    SuggestedAnswer,
    VerificationResult,
)
from copilot.domain.profile import UserProfile
from copilot.generation.prompts import build_system, build_user
from copilot.generation.verifier import AnswerVerifier
from copilot.llm.client import LlmClient
from copilot.research.researcher import relevant_slice


class AnswerGenerator:
    def __init__(self, llm: LlmClient, verifier: AnswerVerifier) -> None:
        self._llm = llm
        self._verifier = verifier

    def generate(
        self,
        *,
        question: DetectedQuestion,
        profile: UserProfile,
        job_context: JobContext | None,
        company: CompanyProfile | None,
        approved_examples: list[str] | None = None,
        extra_instruction: str | None = None,
    ) -> tuple[SuggestedAnswer, VerificationResult]:
        system = build_system(profile)
        company_slice = relevant_slice(company, question.kind) if company else None
        user = build_user(
            question, job_context, company_slice, approved_examples, extra_instruction
        )

        answer = self._llm.generate(
            cached_system=system, user=user, schema=SuggestedAnswer, purpose="answer",
        )
        verification = self._verifier.verify(answer, profile)

        if not verification.ok:
            feedback = "; ".join(verification.issues + verification.unsupported_claims)
            retry_user = user + (
                "\n\n=== CORRECAO OBRIGATORIA ===\n"
                "Sua tentativa anterior continha afirmacoes nao suportadas pelo perfil: "
                f"{feedback}. Reescreva removendo-as ou movendo a lacuna para caveats."
            )
            answer = self._llm.generate(
                cached_system=system, user=retry_user,
                schema=SuggestedAnswer, purpose="answer_retry",
            )
            verification = self._verifier.verify(answer, profile)

        return answer, verification
