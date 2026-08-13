from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from copilot.domain.models import AnswerBundle, DetectedQuestion, JobContext, utcnow


class Stage(StrEnum):
    IDLE = "idle"
    CAPTURING = "capturing"
    OCR = "ocr"
    DETECTING = "detecting"
    EXTRACTING = "extracting"
    RESEARCHING = "researching"
    GENERATING = "generating"
    REVIEW = "review"


class Event(BaseModel):
    at: datetime = Field(default_factory=utcnow)


class PipelineStarted(Event):
    pass


class StageChanged(Event):
    stage: Stage


class ScopeConfirmationNeeded(Event):
    window_title: str | None = None


class QuestionDetected(Event):
    question: DetectedQuestion
    total_found: int = 1


class NoQuestionFound(Event):
    reason: str = "Nenhuma pergunta de formulario detectada nesta tela."


class ContextUpdated(Event):
    context: JobContext


class ResearchStarted(Event):
    company: str


class ResearchReady(Event):
    company: str
    from_cache: bool = False


class AnswerReady(Event):
    bundle: AnswerBundle
    application_id: int | None = None
    question_id: int | None = None
    answer_id: int | None = None


class PipelineError(Event):
    message: str
    stage: Stage = Stage.IDLE


class PipelineCancelled(Event):
    pass


class EventBus:
    """Pub/sub minimo e thread-safe. No MVP conecta core e UI em memoria;
    na V2 os mesmos eventos trafegam por WebSocket."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[Event], None]] = []
        self._lock = threading.Lock()

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def publish(self, event: Event) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for callback in subscribers:
            callback(event)
