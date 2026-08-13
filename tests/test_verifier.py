from copilot.domain.models import SuggestedAnswer
from copilot.generation.verifier import AnswerVerifier, verify_deterministic


def test_valid_answer_passes(sample_profile):
    answer = SuggestedAnswer(
        answer="Na Empresa X mantive APIs em Python com alto volume.",
        facts_used=["exp-001"],
    )
    assert verify_deterministic(answer, sample_profile) == []


def test_unknown_fact_id_is_flagged(sample_profile):
    answer = SuggestedAnswer(answer="Texto.", facts_used=["exp-999"])
    issues = verify_deterministic(answer, sample_profile)
    assert any("exp-999" in issue for issue in issues)


def test_first_person_claim_outside_skills_matrix_is_flagged(sample_profile):
    answer = SuggestedAnswer(
        answer="Tenho experiencia solida com kubernetes em producao ha 3 anos.",
        facts_used=["exp-001"],
    )
    issues = verify_deterministic(answer, sample_profile)
    assert any("kubernetes" in issue for issue in issues)


def test_mentioning_company_tech_without_claim_is_ok(sample_profile):
    answer = SuggestedAnswer(
        answer="Sei que a empresa usa Kubernetes, e tenho interesse em aprender.",
        facts_used=["exp-001"],
    )
    assert verify_deterministic(answer, sample_profile) == []


def test_long_answer_without_facts_is_flagged(sample_profile):
    answer = SuggestedAnswer(answer="palavra " * 60, facts_used=[])
    issues = verify_deterministic(answer, sample_profile)
    assert any("facts_used" in issue for issue in issues)


def test_verifier_without_llm_runs_deterministic_only(sample_profile):
    verifier = AnswerVerifier(llm=None)
    result = verifier.verify(
        SuggestedAnswer(answer="Trabalhei com python na Empresa X.", facts_used=["exp-001"]),
        sample_profile,
    )
    assert result.ok
