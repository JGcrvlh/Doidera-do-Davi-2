"""Fusao acumulativa do JobContext: a descricao da vaga raramente esta na mesma
tela da pergunta, entao o contexto de uma vaga e construido por varias capturas."""

from __future__ import annotations

from copilot.domain.models import JobContext


def _merge_list(current: list[str], incoming: list[str]) -> list[str]:
    seen = {item.casefold().strip() for item in current}
    merged = list(current)
    for item in incoming:
        if item.casefold().strip() not in seen and item.strip():
            merged.append(item.strip())
            seen.add(item.casefold().strip())
    return merged


def merge(current: JobContext, incoming: JobContext) -> JobContext:
    prefer_incoming = incoming.source_confidence > current.source_confidence

    def pick(a, b):
        if a and b:
            return b if prefer_incoming else a
        return a or b

    result = JobContext(
        company=pick(current.company, incoming.company),
        company_domain=pick(current.company_domain, incoming.company_domain),
        role_title=pick(current.role_title, incoming.role_title),
        seniority=(
            incoming.seniority if current.seniority == "unknown" else (
                incoming.seniority
                if prefer_incoming and incoming.seniority != "unknown"
                else current.seniority
            )
        ),
        requirements=_merge_list(current.requirements, incoming.requirements),
        technologies=_merge_list(
            [t.lower() for t in current.technologies],
            [t.lower() for t in incoming.technologies],
        ),
        responsibilities=_merge_list(current.responsibilities, incoming.responsibilities),
        job_description_summary=pick(
            current.job_description_summary, incoming.job_description_summary
        ),
        culture_signals=_merge_list(current.culture_signals, incoming.culture_signals),
        source_confidence=max(current.source_confidence, incoming.source_confidence),
    )
    result.completeness = result.compute_completeness()
    return result
