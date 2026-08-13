"""Maquina de estados do pipeline:

IDLE -> CAPTURING -> OCR -> DETECTING -> EXTRACTING -> [RESEARCHING] -> GENERATING -> REVIEW

Servicos sao injetados (facil trocar por fakes em teste e trocar de transporte
na V2). Chamadas bloqueantes rodam via asyncio.to_thread; o kill switch cancela
a tarefa corrente e descarta capturas.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from copilot.config import Settings
from copilot.context.merger import merge
from copilot.detection import heuristics
from copilot.domain import events as ev
from copilot.domain.models import (
    AnswerBundle,
    JobContext,
    OcrResult,
    RawCapture,
    ScreenAnalysis,
)
from copilot.domain.profile import UserProfile
from copilot.ocr.postprocess import hamming_distance
from copilot.privacy.redactor import redact
from copilot.storage.repository import Repository

log = logging.getLogger(__name__)


class SupportsCapture(Protocol):
    def capture(self) -> RawCapture: ...
    def in_scope(self, window_title: str | None, process_name: str | None) -> bool: ...


class SupportsOcr(Protocol):
    def run(self, capture: RawCapture) -> OcrResult: ...


class SupportsLlmDetect(Protocol):
    def detect(self, redacted_screen_text: str) -> ScreenAnalysis: ...


class SupportsExtract(Protocol):
    def extract(self, redacted_screen_text: str, signals) -> JobContext: ...


class SupportsResearch(Protocol):
    def get_profile(self, context: JobContext): ...


class SupportsGenerate(Protocol):
    def generate(self, **kwargs): ...


class Orchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        bus: ev.EventBus,
        repository: Repository,
        profile: UserProfile,
        capture: SupportsCapture,
        ocr: SupportsOcr,
        llm_detector: SupportsLlmDetect | None,
        extractor: SupportsExtract | None,
        researcher: SupportsResearch | None,
        generator: SupportsGenerate,
        cost_tracker=None,
    ) -> None:
        self._settings = settings
        self._bus = bus
        self._repository = repository
        self._profile = profile
        self._capture = capture
        self._ocr = ocr
        self._llm_detector = llm_detector
        self._extractor = extractor
        self._researcher = researcher
        self._generator = generator
        self._costs = cost_tracker

        self.stage = ev.Stage.IDLE
        self._task: asyncio.Task | None = None
        self._last_ocr: OcrResult | None = None
        self._session_context: JobContext | None = None
        self._last_bundle: tuple[int | None, AnswerBundle] | None = None
        self.allow_out_of_scope = False

    # ------------------------------------------------------------- controle

    def request_analysis(self, loop: asyncio.AbstractEventLoop) -> None:
        """Thread-safe: chamado pelo hotkey/tray."""
        loop.call_soon_threadsafe(self._start_analysis)

    def _start_analysis(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.get_running_loop().create_task(self.analyze())

    def kill(self, loop: asyncio.AbstractEventLoop) -> None:
        def _cancel() -> None:
            if self._task is not None and not self._task.done():
                self._task.cancel()
            self._set_stage(ev.Stage.IDLE)
            self._bus.publish(ev.PipelineCancelled())

        loop.call_soon_threadsafe(_cancel)

    def _set_stage(self, stage: ev.Stage) -> None:
        self.stage = stage
        self._bus.publish(ev.StageChanged(stage=stage))

    # ------------------------------------------------------------- pipeline

    async def analyze(
        self,
        capture: RawCapture | None = None,
        text_override: str | None = None,
    ) -> AnswerBundle | None:
        cost_start = len(self._costs.records) if self._costs else 0
        self._bus.publish(ev.PipelineStarted())
        try:
            ocr = await self._acquire_text(capture, text_override)
            if ocr is None:
                return None

            analysis = await self._detect(ocr)
            if not analysis.questions:
                self._bus.publish(ev.NoQuestionFound())
                self._set_stage(ev.Stage.IDLE)
                return None

            question = analysis.questions[0]
            self._bus.publish(
                ev.QuestionDetected(question=question, total_found=len(analysis.questions))
            )

            context = await self._build_context(ocr, analysis)
            research_task = self._spawn_research(context)

            company_profile = None
            if research_task is not None:
                self._set_stage(ev.Stage.RESEARCHING)
                try:
                    company_profile, from_cache = await research_task
                    if company_profile is not None:
                        self._bus.publish(ev.ResearchReady(
                            company=company_profile.name, from_cache=from_cache,
                        ))
                except Exception as exc:
                    log.warning("Pesquisa de empresa falhou: %s", exc)

            self._set_stage(ev.Stage.GENERATING)
            examples = self._repository.approved_examples()
            suggestion, verification = await asyncio.to_thread(
                self._generator.generate,
                question=question,
                profile=self._profile,
                job_context=context,
                company=company_profile,
                approved_examples=examples,
            )

            cost = self._costs.since(cost_start) if self._costs else 0.0
            bundle = AnswerBundle(
                question=question, suggestion=suggestion,
                verification=verification, cost_usd=cost,
            )
            question_id, answer_id = self._persist(context, bundle)
            self._last_bundle = (question_id, bundle)

            self._set_stage(ev.Stage.REVIEW)
            self._bus.publish(ev.AnswerReady(
                bundle=bundle, question_id=question_id, answer_id=answer_id,
            ))
            return bundle

        except asyncio.CancelledError:
            self._set_stage(ev.Stage.IDLE)
            raise
        except Exception as exc:
            log.exception("Pipeline falhou")
            self._bus.publish(ev.PipelineError(message=str(exc), stage=self.stage))
            self._set_stage(ev.Stage.IDLE)
            return None

    async def _acquire_text(
        self, capture: RawCapture | None, text_override: str | None,
    ) -> OcrResult | None:
        if text_override is not None:
            # Sem OCR: cada linha vira um bloco sintetico para as heuristicas
            from copilot.domain.models import OcrBlock

            lines = [line for line in text_override.splitlines() if line.strip()]
            blocks = [
                OcrBlock(text=line, bbox=(0.0, float(i * 30), 800.0, float(i * 30 + 20)))
                for i, line in enumerate(lines)
            ]
            return OcrResult(blocks=blocks, full_text=text_override)

        self._set_stage(ev.Stage.CAPTURING)
        if capture is None:
            capture = await asyncio.to_thread(self._capture.capture)

        in_scope = self._capture.in_scope(capture.window_title, capture.process_name)
        if not in_scope and not self.allow_out_of_scope:
            self._bus.publish(ev.ScopeConfirmationNeeded(window_title=capture.window_title))
            self._set_stage(ev.Stage.IDLE)
            return None

        self._set_stage(ev.Stage.OCR)
        ocr = await asyncio.to_thread(self._ocr.run, capture)

        if (
            self._last_ocr is not None
            and ocr.image_hash and self._last_ocr.image_hash
            and hamming_distance(ocr.image_hash, self._last_ocr.image_hash)
            <= self._settings.screen_diff_threshold
        ):
            ocr = self._last_ocr
        else:
            self._last_ocr = ocr
        return ocr

    async def _detect(self, ocr: OcrResult) -> ScreenAnalysis:
        self._set_stage(ev.Stage.DETECTING)
        analysis = heuristics.analyze(ocr)
        if heuristics.is_ambiguous(analysis, ocr) and self._llm_detector is not None:
            redacted = self._redact(ocr.full_text)
            llm_analysis = await asyncio.to_thread(self._llm_detector.detect, redacted)
            if llm_analysis.questions:
                llm_analysis.platform_hint = (
                    llm_analysis.platform_hint or analysis.platform_hint
                )
                if llm_analysis.job_signals.is_empty():
                    llm_analysis.job_signals = analysis.job_signals
                return llm_analysis
        return analysis

    async def _build_context(self, ocr: OcrResult, analysis: ScreenAnalysis) -> JobContext:
        self._set_stage(ev.Stage.EXTRACTING)
        extracted = JobContext()
        if self._extractor is not None and (
            not analysis.job_signals.is_empty() or len(ocr.full_text) > 300
        ):
            redacted = self._redact(ocr.full_text)
            extracted = await asyncio.to_thread(
                self._extractor.extract, redacted, analysis.job_signals
            )

        context = extracted
        if self._session_context is not None:
            context = merge(self._session_context, extracted)
        stored = self._repository.get_job_context(context.company, context.role_title)
        if stored is not None:
            context = merge(stored, context)

        self._session_context = context
        self._bus.publish(ev.ContextUpdated(context=context))
        return context

    def _spawn_research(self, context: JobContext) -> asyncio.Task | None:
        if self._researcher is None or not context.company:
            return None
        self._bus.publish(ev.ResearchStarted(company=context.company))
        return asyncio.get_running_loop().create_task(
            asyncio.to_thread(self._researcher.get_profile, context)
        )

    def _redact(self, textv: str) -> str:
        if not self._settings.redact_before_send:
            return textv
        return redact(textv).text

    def _persist(self, context: JobContext, bundle: AnswerBundle) -> tuple[int | None, int | None]:
        try:
            application_id = self._repository.upsert_application(context)
            question_id = self._repository.save_question(application_id, bundle.question)
            answer_id = self._repository.save_answer(question_id, bundle)
            return question_id, answer_id
        except Exception:
            log.exception("Falha ao persistir resposta")
            return None, None

    # ----------------------------------------------------- acoes da revisao

    async def regenerate(self, instruction: str | None = None) -> AnswerBundle | None:
        """Regenera a ultima resposta com uma instrucao extra ('mais curto'...)."""
        if self._last_bundle is None:
            return None
        question_id, previous = self._last_bundle
        cost_start = len(self._costs.records) if self._costs else 0
        self._set_stage(ev.Stage.GENERATING)
        try:
            company = None
            if self._researcher is not None and self._session_context is not None:
                company, _ = await asyncio.to_thread(
                    self._researcher.get_profile, self._session_context
                )
            suggestion, verification = await asyncio.to_thread(
                self._generator.generate,
                question=previous.question,
                profile=self._profile,
                job_context=self._session_context,
                company=company,
                approved_examples=self._repository.approved_examples(),
                extra_instruction=instruction,
            )
            bundle = AnswerBundle(
                question=previous.question, suggestion=suggestion,
                verification=verification,
                cost_usd=self._costs.since(cost_start) if self._costs else 0.0,
            )
            answer_id = None
            if question_id is not None:
                answer_id = self._repository.save_answer(question_id, bundle)
            self._last_bundle = (question_id, bundle)
            self._set_stage(ev.Stage.REVIEW)
            self._bus.publish(ev.AnswerReady(
                bundle=bundle, question_id=question_id, answer_id=answer_id,
            ))
            return bundle
        except Exception as exc:
            log.exception("Regeneracao falhou")
            self._bus.publish(ev.PipelineError(message=str(exc), stage=self.stage))
            self._set_stage(ev.Stage.IDLE)
            return None

    def save_final(self, answer_id: int, final_text: str) -> None:
        self._repository.update_final_answer(answer_id, final_text)
