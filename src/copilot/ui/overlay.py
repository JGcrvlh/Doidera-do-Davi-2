from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from copilot.domain.events import AnswerReady


class OverlayPanel(QWidget):
    """Painel discreto de revisao: mostra a sugestao com justificativa, fatos
    usados e ressalvas. Copiar poe na area de transferencia e salva a versao
    final — nada e preenchido ou enviado automaticamente."""

    def __init__(
        self,
        *,
        on_copy_final: Callable[[int | None, str], None],
        on_regenerate: Callable[[str | None], None],
    ) -> None:
        super().__init__()
        self._on_copy_final = on_copy_final
        self._on_regenerate = on_regenerate
        self._answer_id: int | None = None

        self.setObjectName("overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)

        self._question = QLabel()
        self._question.setObjectName("question")
        self._question.setWordWrap(True)
        layout.addWidget(self._question)

        self._status = QLabel()
        self._status.setObjectName("meta")
        layout.addWidget(self._status)

        self._answer = QTextEdit()
        self._answer.setMinimumHeight(180)
        layout.addWidget(self._answer)

        self._warning = QLabel()
        self._warning.setObjectName("warning")
        self._warning.setWordWrap(True)
        self._warning.hide()
        layout.addWidget(self._warning)

        self._meta = QLabel()
        self._meta.setObjectName("meta")
        self._meta.setWordWrap(True)
        layout.addWidget(self._meta)

        buttons = QHBoxLayout()
        copy_btn = QPushButton("Copiar")
        copy_btn.clicked.connect(self._copy)
        regen_btn = QPushButton("Regenerar...")
        regen_btn.setObjectName("secondary")
        regen_btn.clicked.connect(self._regenerate)
        close_btn = QPushButton("Descartar")
        close_btn.setObjectName("secondary")
        close_btn.clicked.connect(self.hide)
        buttons.addWidget(copy_btn)
        buttons.addWidget(regen_btn)
        buttons.addStretch()
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        self._drag_offset = None

    # ------------------------------------------------------------- conteudo

    def show_working(self, message: str) -> None:
        self._status.setText(message)
        if not self.isVisible():
            self._place()
            self.show()

    def show_answer(self, event: AnswerReady) -> None:
        bundle = event.bundle
        self._answer_id = event.answer_id
        self._question.setText(bundle.question.text)
        self._answer.setPlainText(bundle.suggestion.answer)
        self._status.setText("")

        problems = bundle.verification.issues + bundle.verification.unsupported_claims
        if problems:
            self._warning.setText(
                "⚠ Verificacao encontrou pontos nao suportados pelo seu perfil:\n- "
                + "\n- ".join(problems[:4])
            )
            self._warning.show()
        else:
            self._warning.hide()

        meta_parts = []
        if bundle.suggestion.facts_used:
            meta_parts.append("Fatos: " + ", ".join(bundle.suggestion.facts_used))
        if bundle.suggestion.caveats:
            meta_parts.append("Ressalvas: " + " | ".join(bundle.suggestion.caveats[:3]))
        if bundle.suggestion.rationale:
            meta_parts.append("Por que assim: " + bundle.suggestion.rationale)
        meta_parts.append(
            f"Confianca: {bundle.suggestion.confidence} · custo ~US$ {bundle.cost_usd:.3f}"
        )
        self._meta.setText("\n".join(meta_parts))

        self._place()
        self.show()
        self.raise_()

    def show_error(self, message: str) -> None:
        self._status.setText(f"Erro: {message}")
        self._place()
        self.show()

    def _place(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(screen.right() - self.width() - 24, screen.top() + 60)

    # --------------------------------------------------------------- acoes

    def _copy(self) -> None:
        final_text = self._answer.toPlainText()
        QApplication.clipboard().setText(final_text)
        self._on_copy_final(self._answer_id, final_text)
        self._status.setText("Copiado ✓ — revise antes de enviar.")

    def _regenerate(self) -> None:
        instruction, ok = QInputDialog.getText(
            self, "Regenerar", "Instrucao (opcional, ex.: 'mais curto'):"
        )
        self._on_regenerate(instruction.strip() or None if ok else None)
        if ok:
            self._status.setText("Regenerando...")

    # ------------------------------------------------- arrastar com o mouse

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _event) -> None:
        self._drag_offset = None
