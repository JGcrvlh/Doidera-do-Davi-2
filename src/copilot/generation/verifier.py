"""Camada 2 do anti-alucinacao: verificacao pos-geracao.

1) Checagem deterministica local: IDs citados existem? Ha tecnologia afirmada em
   primeira pessoa fora da skills_matrix?
2) Checagem semantica (Haiku): afirmacoes factuais da resposta sao suportadas
   pelos fatos citados?
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from copilot.domain.models import SuggestedAnswer, VerificationResult
from copilot.domain.profile import UserProfile
from copilot.llm.client import LlmClient

TECH_VOCAB = {
    "python", "java", "javascript", "typescript", "go", "golang", "rust", "c++", "c#",
    "ruby", "php", "kotlin", "swift", "scala", "elixir", "django", "flask", "fastapi",
    "spring", "react", "angular", "vue", "svelte", "node", "nodejs", "next.js", "nestjs",
    "rails", "laravel", "postgres", "postgresql", "mysql", "mongodb", "redis", "kafka",
    "rabbitmq", "elasticsearch", "sqlite", "oracle", "dynamodb", "aws", "azure", "gcp",
    "docker", "kubernetes", "k8s", "terraform", "ansible", "jenkins", "git", "linux",
    "graphql", "grpc", "spark", "airflow", "pandas", "numpy", "pytorch", "tensorflow",
    "scikit-learn", "dbt", "snowflake", "databricks", "flutter", "react native",
}

_FIRST_PERSON_EXPERIENCE = (
    r"(?:trabalhei|usei|utilizei|desenvolvi|implementei|programei|criei|construi|"
    r"construí|mantive|dominava?|tenho experi[eê]ncia|possuo experi[eê]ncia|"
    r"sou (?:proficiente|especialista)|worked with|i used|i built|i developed|"
    r"experienced (?:in|with)|proficient in)"
)


class _SemanticCheck(BaseModel):
    all_supported: bool
    unsupported_claims: list[str] = []


_SEMANTIC_SYSTEM = """Voce e um verificador de fatos. Recebera (a) fatos reais do perfil de um
candidato e (b) uma resposta de candidatura escrita em nome dele.

Liste toda afirmacao FACTUAL sobre o candidato (experiencias, numeros, tecnologias, cargos,
resultados) que NAO e suportada pelos fatos dados. Parafrasear e resumir e permitido; inventar,
exagerar numeros ou elevar nivel de dominio NAO e. Opinioes, motivacao e planos futuros nao
precisam de suporte."""


def _techs_claimed_first_person(text: str) -> set[str]:
    lowered = text.lower()
    claimed: set[str] = set()
    for tech in TECH_VOCAB:
        pattern = _FIRST_PERSON_EXPERIENCE + r"[^.!?\n]{0,80}?" + re.escape(tech) + r"\b"
        if re.search(pattern, lowered):
            claimed.add(tech)
    return claimed


def verify_deterministic(answer: SuggestedAnswer, profile: UserProfile) -> list[str]:
    issues: list[str] = []

    valid_ids = profile.all_fact_ids()
    for fact_id in answer.facts_used:
        if fact_id not in valid_ids:
            issues.append(f"facts_used cita id inexistente no perfil: '{fact_id}'")

    if not answer.facts_used and len(answer.answer) > 200:
        issues.append("Resposta longa sem nenhum fato do perfil citado em facts_used")

    known = profile.known_technologies()
    for tech in _techs_claimed_first_person(answer.answer):
        if tech not in known:
            issues.append(
                f"Afirma experiencia em primeira pessoa com '{tech}', que nao esta na skills_matrix"
            )
    return issues


class AnswerVerifier:
    def __init__(self, llm: LlmClient | None) -> None:
        self._llm = llm

    def verify(self, answer: SuggestedAnswer, profile: UserProfile) -> VerificationResult:
        issues = verify_deterministic(answer, profile)
        unsupported: list[str] = []

        if self._llm is not None and answer.answer.strip():
            facts = profile.facts_by_id()
            cited = {
                fid: facts[fid] for fid in answer.facts_used if fid in facts
            } or facts
            facts_text = "\n".join(
                f"[{fid}] " + " | ".join(items) for fid, items in cited.items()
            )
            try:
                check = self._llm.extract(
                    system=_SEMANTIC_SYSTEM,
                    user=(
                        f"FATOS DO PERFIL:\n{facts_text}\n\n"
                        f"RESPOSTA A VERIFICAR:\n{answer.answer}"
                    ),
                    schema=_SemanticCheck,
                    purpose="verification",
                )
                if not check.all_supported:
                    unsupported = check.unsupported_claims
            except Exception as exc:  # verificacao semantica nunca derruba o pipeline
                issues.append(f"Verificacao semantica indisponivel: {exc}")

        return VerificationResult(
            ok=not issues and not unsupported,
            issues=issues,
            unsupported_claims=unsupported,
        )
