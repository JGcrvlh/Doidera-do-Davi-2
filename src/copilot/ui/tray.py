from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from copilot.domain.events import Stage

_STAGE_COLORS = {
    Stage.IDLE: "#6b7280",
    Stage.CAPTURING: "#f59e0b",
    Stage.OCR: "#f59e0b",
    Stage.DETECTING: "#f59e0b",
    Stage.EXTRACTING: "#3b82f6",
    Stage.RESEARCHING: "#3b82f6",
    Stage.GENERATING: "#8b5cf6",
    Stage.REVIEW: "#10b981",
}


def _dot_icon(color: str) -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(QColor(color).darker(140))
    painter.drawEllipse(4, 4, 24, 24)
    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    """Ponto de presenca do app: estado visivel (o app nunca trabalha
    'invisivel'), armar/pausar, analisar, historico e kill switch."""

    def __init__(
        self,
        *,
        on_analyze: Callable[[], None],
        on_toggle_armed: Callable[[bool], None],
        on_history: Callable[[], None],
        on_kill: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        super().__init__(_dot_icon(_STAGE_COLORS[Stage.IDLE]))
        self._armed = False
        self._on_toggle_armed = on_toggle_armed

        menu = QMenu()
        self._arm_action = QAction("Armar captura")
        self._arm_action.setCheckable(True)
        self._arm_action.toggled.connect(self._toggle)
        menu.addAction(self._arm_action)

        analyze = QAction("Analisar tela agora")
        analyze.triggered.connect(lambda: on_analyze())
        menu.addAction(analyze)

        history = QAction("Historico...")
        history.triggered.connect(lambda: on_history())
        menu.addAction(history)

        menu.addSeparator()
        kill = QAction("Parar tudo (kill switch)")
        kill.triggered.connect(lambda: on_kill())
        menu.addAction(kill)

        quit_action = QAction("Sair")
        quit_action.triggered.connect(lambda: on_quit())
        menu.addAction(quit_action)

        self._menu = menu
        self._actions = [analyze, history, kill, quit_action]
        self.setContextMenu(menu)
        self.setToolTip("Candidate Copilot — pausado")

    def _toggle(self, checked: bool) -> None:
        self._armed = checked
        self.setToolTip(
            "Candidate Copilot — armado" if checked else "Candidate Copilot — pausado"
        )
        self._on_toggle_armed(checked)

    def set_stage(self, stage: Stage) -> None:
        self.setIcon(_dot_icon(_STAGE_COLORS.get(stage, "#6b7280")))

    def notify(self, title: str, message: str) -> None:
        self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)
