"""Teste de integracao do Orchestrator com servicos falsos: valida o fluxo
captura -> ocr -> deteccao -> contexto -> pesquisa -> geracao -> persistencia
e a ordem dos eventos, sem tocar em rede, tela ou modelos."""

from __future__ import annotations

import asyncio

import pytest

from copilot.config import Settings
from copilot.domain import events as ev
from copilot.domain.models import (
    CompanyProfile,
    FitAnalysis,
    JobContext,
    OcrBlock,
    OcrResult,
    RawCapture,
    SuggestedAnswer,
)
from copilot.orchestrator.pipeline import Orchestrator
from copilot.storage.db import create_db
from copilot.storage.repository import Repository

SCREEN_LINES = [
    "Vaga: Desenvolvedor Backend Pleno - Empresa X",
    "Requisitos: Python, FastAPI, 3 anos de experiencia",
    "Por que voce quer trabalhar na Empresa X?",
]


class FakeCapture:
    def capture(self) -> RawCapture:
        return RawCapture(png=b"png", width=800, height=600, window_title="Gupy - Empresa X")

    def in_scope(self, window_title, _process):
        return "gupy" in (window_title or "").lower()


class FakeOcr:
    def run(self, _capture) -> OcrResult:
        blocks = [
            OcrBlock(text=line, bbox=(10, 10 + i * 40, 700, 30 + i * 40))
            for i, line in enumerate(SCREEN_LINES)
        ]
        return OcrResult(blocks=blocks, full_text="\n".join(SCREEN_LINES))


class FakeExtractor:
    def extract(self, _text, _signals) -> JobContext:
        return JobContext(
            company="Empresa X", role_title="Desenvolvedor Backend Pleno",
            technologies=["python", "fastapi"], source_confidence=0.9,
        )


class FakeResearcher:
    calls = 0

    def get_profile(self, context):
        FakeResearcher.calls += 1
        return CompanyProfile(name=context.company, summary="Fintech"), False


class FakeGenerator:
    def generate(self, *, question, profile, job_context, company, **_kwargs):
        from copilot.domain.models import VerificationResult

        assert company is not None and company.name == "Empresa X"
        assert job_context.company == "Empresa X"
        answer = SuggestedAnswer(
            fit_analysis=FitAnalysis(angle="python match"),
            answer="Quero trabalhar na Empresa X porque uso Python diariamente.",
            facts_used=["exp-001"],
            confidence="high",
        )
        return answer, VerificationResult(ok=True)


@pytest.fixture
def orchestrator(tmp_path, sample_profile):
    _, session_factory = create_db(tmp_path / "p.db")
    repository = Repository(session_factory)
    bus = ev.EventBus()
    events: list[ev.Event] = []
    bus.subscribe(events.append)
    orch = Orchestrator(
        settings=Settings(data_dir=tmp_path),
        bus=bus,
        repository=repository,
        profile=sample_profile,
        capture=FakeCapture(),
        ocr=FakeOcr(),
        llm_detector=None,
        extractor=FakeExtractor(),
        researcher=FakeResearcher(),
        generator=FakeGenerator(),
    )
    return orch, events, repository


def test_full_pipeline_flow(orchestrator):
    orch, events, repository = orchestrator
    bundle = asyncio.run(orch.analyze())

    assert bundle is not None
    assert "Empresa X" in bundle.suggestion.answer
    assert bundle.question.kind == "motivation"

    event_types = [type(e).__name__ for e in events]
    assert "PipelineStarted" in event_types
    assert "QuestionDetected" in event_types
    assert "ContextUpdated" in event_types
    assert "ResearchStarted" in event_types
    assert "AnswerReady" in event_types
    assert event_types.index("QuestionDetected") < event_types.index("AnswerReady")

    # Persistencia: aplicacao + pergunta + resposta gravadas
    apps = repository.list_applications()
    assert len(apps) == 1
    assert apps[0].company == "Empresa X"
    answer_ready = next(e for e in events if isinstance(e, ev.AnswerReady))
    assert answer_ready.answer_id is not None


def test_out_of_scope_asks_confirmation(orchestrator, monkeypatch):
    orch, events, _repo = orchestrator
    monkeypatch.setattr(
        FakeCapture, "capture",
        lambda self: RawCapture(png=b"x", width=10, height=10, window_title="Banco Online"),
    )
    bundle = asyncio.run(orch.analyze())
    assert bundle is None
    assert any(isinstance(e, ev.ScopeConfirmationNeeded) for e in events)
    assert not any(isinstance(e, ev.AnswerReady) for e in events)


def test_text_override_skips_capture(orchestrator):
    orch, events, _repo = orchestrator
    text = "\n".join(SCREEN_LINES)
    bundle = asyncio.run(orch.analyze(text_override=text))
    assert bundle is not None
    assert not any(
        isinstance(e, ev.StageChanged) and e.stage == ev.Stage.CAPTURING for e in events
    )


def test_no_question_found(orchestrator):
    orch, events, _repo = orchestrator
    bundle = asyncio.run(orch.analyze(text_override="Pagina institucional sem formularios."))
    assert bundle is None
    assert any(isinstance(e, ev.NoQuestionFound) for e in events)
