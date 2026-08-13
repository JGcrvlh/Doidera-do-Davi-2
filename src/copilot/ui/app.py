"""Wiring da aplicacao grafica.

A UI (Qt) roda no thread principal; o pipeline roda num event loop asyncio em
thread separado. A ponte e uma fila thread-safe drenada por QTimer — o mesmo
modelo de eventos que, na V2, passa a trafegar por WebSocket.
"""

from __future__ import annotations

import asyncio
import contextlib
import queue
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from copilot.capture.hotkeys import HotkeyManager
from copilot.capture.screen import CaptureService
from copilot.config import Settings
from copilot.context.extractor import ContextExtractor
from copilot.detection.llm_detector import LlmQuestionDetector
from copilot.domain import events as ev
from copilot.domain.profile import ProfileError, load_profile
from copilot.generation.generator import AnswerGenerator
from copilot.generation.verifier import AnswerVerifier
from copilot.llm.client import LlmClient
from copilot.ocr.rapidocr import RapidOcrService
from copilot.orchestrator.pipeline import Orchestrator
from copilot.research.researcher import CompanyResearcher
from copilot.storage.db import create_db
from copilot.storage.repository import Repository
from copilot.ui.history import HistoryWindow
from copilot.ui.overlay import OverlayPanel
from copilot.ui.tray import TrayIcon

_STAGE_MESSAGES = {
    ev.Stage.CAPTURING: "Capturando a tela...",
    ev.Stage.OCR: "Lendo o texto (OCR local)...",
    ev.Stage.DETECTING: "Procurando a pergunta...",
    ev.Stage.EXTRACTING: "Entendendo a vaga...",
    ev.Stage.RESEARCHING: "Pesquisando a empresa...",
    ev.Stage.GENERATING: "Escrevendo a sugestao...",
}


class CopilotApp:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        settings.ensure_dirs()

        profile_path = settings.resolved_profile_path()
        try:
            self._profile = load_profile(profile_path)
        except ProfileError as error:
            self._fail_at_startup(str(error))
            raise SystemExit(1) from error

        _, session_factory = create_db(settings.db_path)
        self._repository = Repository(session_factory)

        llm = LlmClient(settings)
        verifier = AnswerVerifier(llm)
        self._orchestrator = Orchestrator(
            settings=settings,
            bus=self._make_bus(),
            repository=self._repository,
            profile=self._profile,
            capture=CaptureService(settings),
            ocr=RapidOcrService(settings),
            llm_detector=LlmQuestionDetector(llm),
            extractor=ContextExtractor(llm),
            researcher=CompanyResearcher(llm, self._repository, settings.research_ttl_days),
            generator=AnswerGenerator(llm, verifier),
            cost_tracker=llm.costs,
        )

        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever, name="copilot-core", daemon=True
        )

    # ------------------------------------------------------------- bootstrap

    def _make_bus(self) -> ev.EventBus:
        self._event_queue: queue.Queue[ev.Event] = queue.Queue()
        bus = ev.EventBus()
        bus.subscribe(self._event_queue.put)
        return bus

    @staticmethod
    def _fail_at_startup(message: str) -> None:
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Candidate Copilot", message)
        del app

    def run(self) -> int:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        style_path = Path(__file__).parent / "styles.qss"
        if style_path.exists():
            app.setStyleSheet(style_path.read_text(encoding="utf-8"))

        self._overlay = OverlayPanel(
            on_copy_final=self._save_final,
            on_regenerate=self._regenerate,
        )
        self._history = HistoryWindow(self._repository)
        self._tray = TrayIcon(
            on_analyze=self._analyze,
            on_toggle_armed=self._toggle_armed,
            on_history=self._history.show,
            on_kill=self._kill,
            on_quit=app.quit,
        )
        self._tray.show()

        self._hotkeys = HotkeyManager()
        self._hotkeys.bind(self._settings.hotkey_analyze, self._analyze_if_armed)
        self._hotkeys.bind(self._settings.hotkey_kill, self._kill)

        self._armed = False
        self._loop_thread.start()

        timer = QTimer()
        timer.timeout.connect(self._drain_events)
        timer.start(50)

        self._tray.notify(
            "Candidate Copilot",
            "Iniciado em modo pausado. Arme a captura no icone da bandeja.",
        )

        code = app.exec()
        self._shutdown()
        return code

    def _shutdown(self) -> None:
        with contextlib.suppress(Exception):
            self._hotkeys.stop()
        self._loop.call_soon_threadsafe(self._loop.stop)

    # --------------------------------------------------------------- acoes

    def _toggle_armed(self, armed: bool) -> None:
        self._armed = armed
        if armed:
            try:
                self._hotkeys.start()
            except Exception as error:
                self._tray.notify("Hotkey indisponivel", str(error))
        else:
            self._hotkeys.stop()

    def _analyze_if_armed(self) -> None:
        if self._armed:
            self._analyze()

    def _analyze(self) -> None:
        self._orchestrator.request_analysis(self._loop)

    def _kill(self) -> None:
        self._orchestrator.kill(self._loop)
        self._overlay.hide()

    def _regenerate(self, instruction: str | None) -> None:
        asyncio.run_coroutine_threadsafe(
            self._orchestrator.regenerate(instruction), self._loop
        )

    def _save_final(self, answer_id: int | None, final_text: str) -> None:
        if answer_id is not None:
            self._orchestrator.save_final(answer_id, final_text)

    # -------------------------------------------------------------- eventos

    def _drain_events(self) -> None:
        while True:
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                return
            self._handle_event(event)

    def _handle_event(self, event: ev.Event) -> None:
        if isinstance(event, ev.StageChanged):
            self._tray.set_stage(event.stage)
            message = _STAGE_MESSAGES.get(event.stage)
            if message:
                self._overlay.show_working(message)
        elif isinstance(event, ev.AnswerReady):
            self._overlay.show_answer(event)
        elif isinstance(event, ev.NoQuestionFound):
            self._tray.notify("Nada encontrado", event.reason)
            self._overlay.hide()
        elif isinstance(event, ev.ScopeConfirmationNeeded):
            self._confirm_scope(event)
        elif isinstance(event, ev.PipelineError):
            self._overlay.show_error(event.message)
        elif isinstance(event, ev.PipelineCancelled):
            self._overlay.hide()

    def _confirm_scope(self, event: ev.ScopeConfirmationNeeded) -> None:
        title = event.window_title or "(janela desconhecida)"
        answer = QMessageBox.question(
            None,
            "Fora do escopo de candidatura",
            f'A janela ativa "{title}" nao parece uma pagina de candidatura.\n'
            "Analisar mesmo assim?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._orchestrator.allow_out_of_scope = True
            self._analyze()
            self._orchestrator.allow_out_of_scope = False


def run_gui(settings: Settings) -> int:
    return CopilotApp(settings).run()
