from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from copilot.storage.repository import Repository


class HistoryWindow(QMainWindow):
    """Historico pesquisavel (FTS5): vagas, perguntas e respostas."""

    def __init__(self, repository: Repository) -> None:
        super().__init__()
        self._repository = repository
        self.setWindowTitle("Candidate Copilot — Historico")
        self.resize(860, 520)

        root = QWidget()
        layout = QVBoxLayout(root)

        search_bar = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText("Buscar (ex.: lideranca, python, nome da empresa)...")
        self._query.returnPressed.connect(self.refresh)
        search_button = QPushButton("Buscar")
        search_button.clicked.connect(self.refresh)
        search_bar.addWidget(self._query)
        search_bar.addWidget(search_button)
        layout.addLayout(search_bar)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Empresa", "Vaga", "Pergunta"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.itemSelectionChanged.connect(self._show_detail)
        layout.addWidget(self._table, stretch=2)

        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        layout.addWidget(self._detail, stretch=1)

        self.setCentralWidget(root)
        self._hits = []

    def refresh(self) -> None:
        query = self._query.text().strip()
        self._hits = self._repository.search(query or "a", limit=100)
        self._table.setRowCount(len(self._hits))
        for row, hit in enumerate(self._hits):
            self._table.setItem(row, 0, QTableWidgetItem(hit.company))
            self._table.setItem(row, 1, QTableWidgetItem(hit.role))
            self._table.setItem(row, 2, QTableWidgetItem(hit.question_text[:120]))

    def _show_detail(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows or rows[0].row() >= len(self._hits):
            return
        hit = self._hits[rows[0].row()]
        self._detail.setPlainText(
            f"{hit.company} — {hit.role}\n\nPergunta:\n{hit.question_text}\n\n"
            f"Resposta:\n{hit.answer_text}"
        )

    def showEvent(self, event) -> None:
        self.refresh()
        super().showEvent(event)
