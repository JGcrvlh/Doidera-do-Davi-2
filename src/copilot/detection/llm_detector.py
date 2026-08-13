"""Camada 2 da deteccao: fallback com modelo pequeno para telas ambiguas.

Recebe SOMENTE texto ja redigido pelo Redactor.
"""

from __future__ import annotations

from copilot.domain.models import ScreenAnalysis
from copilot.llm.client import LlmClient

_SYSTEM = """Voce analisa o texto extraido (OCR) da tela de um formulario de candidatura a emprego.
Identifique as perguntas dirigidas AO CANDIDATO (campos que ele precisa responder), o tipo de cada
uma e sinais sobre a vaga (requisitos, cultura, titulo do cargo) presentes no texto.

Regras:
- NAO invente perguntas: se nao houver campo claro dirigido ao candidato, retorne lista vazia.
- Ignore navegacao, botoes, rodapes e texto institucional.
- char_limit somente se explicito no texto (ex.: "maximo 500 caracteres")."""


class LlmQuestionDetector:
    def __init__(self, llm: LlmClient) -> None:
        self._llm = llm

    def detect(self, redacted_screen_text: str) -> ScreenAnalysis:
        return self._llm.extract(
            system=_SYSTEM,
            user=f"Texto da tela (OCR):\n\n{redacted_screen_text}",
            schema=ScreenAnalysis,
        )
