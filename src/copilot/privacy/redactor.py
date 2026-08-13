"""Unico caminho de saida para a rede: todo texto enviado a APIs passa por aqui.

Remove PII que nao pertence ao processo seletivo. Os dados do proprio candidato
que a resposta precisa vem do profile.yaml, nao da tela — entao redigir a tela
nao degrada o resultado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")),
    ("CPF", re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")),
    ("CNPJ", re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")),
    ("CARTAO", re.compile(r"\b(?:\d[ -]?){13,19}\b(?=[^\d]|$)")),
    # Telefones BR: +55 11 91234-5678 / (11) 91234-5678 / 11 3123-4567
    ("TELEFONE", re.compile(
        r"(?:(?<=\s)|^)(?:\+?55[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?)?9?\d{4}[\s.-]\d{4}\b"
    )),
    ("CEP", re.compile(r"\b\d{5}-\d{3}\b")),
]


@dataclass
class RedactionReport:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact(text: str) -> RedactionReport:
    counts: dict[str, int] = {}
    result = text
    for label, pattern in _PATTERNS:
        result, n = pattern.subn(f"[{label}]", result)
        if n:
            counts[label] = counts.get(label, 0) + n
    return RedactionReport(text=result, counts=counts)
