from datetime import UTC, datetime, timedelta

import pytest

from copilot.domain.models import (
    AnswerBundle,
    CompanyProfile,
    DetectedQuestion,
    JobContext,
    SuggestedAnswer,
    VerificationResult,
)
from copilot.storage.db import create_db
from copilot.storage.repository import Repository


@pytest.fixture
def repo(tmp_path):
    _, session_factory = create_db(tmp_path / "test.db")
    return Repository(session_factory)


def _bundle(text="Resposta gerada sobre python.") -> AnswerBundle:
    return AnswerBundle(
        question=DetectedQuestion(text="Por que voce quer essa vaga?", kind="motivation"),
        suggestion=SuggestedAnswer(answer=text, facts_used=["exp-001"], rationale="r"),
        verification=VerificationResult(ok=True),
        cost_usd=0.05,
    )


def test_application_roundtrip(repo):
    context = JobContext(company="Empresa X", role_title="Backend", requirements=["Python"])
    app_id = repo.upsert_application(context)
    loaded = repo.get_job_context("Empresa X", "Backend")
    assert loaded is not None
    assert loaded.requirements == ["Python"]

    context.requirements.append("Docker")
    assert repo.upsert_application(context) == app_id  # upsert, nao duplica


def test_question_dedup_and_answers(repo):
    app_id = repo.upsert_application(JobContext(company="X", role_title="Dev"))
    bundle = _bundle()
    q1 = repo.save_question(app_id, bundle.question)
    q2 = repo.save_question(app_id, bundle.question)
    assert q1 == q2

    answer_id = repo.save_answer(q1, bundle)
    repo.update_final_answer(answer_id, "Versao editada pelo usuario.")
    assert repo.approved_examples() == ["Versao editada pelo usuario."]


def test_search_finds_answer(repo):
    app_id = repo.upsert_application(JobContext(company="Empresa X", role_title="Dev"))
    q_id = repo.save_question(app_id, _bundle().question)
    repo.save_answer(q_id, _bundle("Minha experiencia com lideranca tecnica."))
    hits = repo.search("lideranca")
    assert len(hits) == 1
    assert hits[0].company == "Empresa X"


def test_company_cache_roundtrip(repo):
    profile = CompanyProfile(name="Empresa X", summary="Fintech brasileira")
    repo.set_company_cache("empresax.com", profile)
    loaded = repo.get_company_cache("empresax.com")
    assert loaded is not None
    assert loaded.name == "Empresa X"
    assert loaded.researched_at.tzinfo is not None
    assert datetime.now(UTC) - loaded.researched_at < timedelta(minutes=1)
    assert repo.get_company_cache("outra.com") is None


def test_delete_all(repo):
    app_id = repo.upsert_application(JobContext(company="X", role_title="Dev"))
    q_id = repo.save_question(app_id, _bundle().question)
    repo.save_answer(q_id, _bundle())
    repo.delete_all()
    assert repo.list_applications() == []
    assert repo.search("python") == []
