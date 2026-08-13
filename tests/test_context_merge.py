from copilot.context.merger import merge
from copilot.domain.models import JobContext


def test_merge_fills_gaps():
    stored = JobContext(company="Empresa X", requirements=["Python"], source_confidence=0.8)
    incoming = JobContext(role_title="Backend Pleno", technologies=["python"],
                          source_confidence=0.6)
    result = merge(stored, incoming)
    assert result.company == "Empresa X"
    assert result.role_title == "Backend Pleno"
    assert result.requirements == ["Python"]
    assert result.technologies == ["python"]


def test_merge_prefers_higher_confidence_on_conflict():
    stored = JobContext(role_title="Dev Junior", source_confidence=0.5)
    incoming = JobContext(role_title="Dev Pleno", source_confidence=0.9)
    assert merge(stored, incoming).role_title == "Dev Pleno"

    stored_high = JobContext(role_title="Dev Junior", source_confidence=0.9)
    incoming_low = JobContext(role_title="Dev Pleno", source_confidence=0.5)
    assert merge(stored_high, incoming_low).role_title == "Dev Junior"


def test_merge_dedups_lists_case_insensitive():
    a = JobContext(requirements=["Python avancado", "Ingles"], source_confidence=0.7)
    b = JobContext(requirements=["python avancado", "Docker"], source_confidence=0.7)
    result = merge(a, b)
    assert result.requirements == ["Python avancado", "Ingles", "Docker"]


def test_merge_seniority_unknown_is_replaced():
    a = JobContext(seniority="unknown", source_confidence=0.9)
    b = JobContext(seniority="senior", source_confidence=0.3)
    assert merge(a, b).seniority == "senior"


def test_completeness_recomputed():
    a = JobContext(company="X", source_confidence=0.5)
    b = JobContext(role_title="Dev", requirements=["r"], technologies=["t"],
                   job_description_summary="s", seniority="mid", source_confidence=0.5)
    result = merge(a, b)
    assert result.completeness == 1.0
