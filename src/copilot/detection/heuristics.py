"""Camada 1 da deteccao: regras locais, custo zero. Resolve a maioria das telas;
o que ficar ambiguo vai para o fallback LLM (llm_detector)."""

from __future__ import annotations

import re

from copilot.domain.models import (
    DetectedQuestion,
    JobSignals,
    OcrResult,
    QuestionKind,
    ScreenAnalysis,
)

_QUESTION_STARTERS = (
    "por que", "por quê", "porque voce", "porque você", "descreva", "conte",
    "explique", "fale sobre", "cite", "como voce", "como você", "o que te",
    "o que voce", "o que você", "qual", "quais", "se voce", "se você",
    "why", "describe", "tell us", "tell me", "explain", "what makes", "what is your",
    "how did you", "how would you", "share",
)

_CHAR_LIMIT_PATTERNS = (
    re.compile(r"m[aá]x(?:imo)?\.?\s*(?:de\s*)?(\d{2,5})\s*caracteres", re.IGNORECASE),
    re.compile(r"max(?:imum)?\s*(?:of\s*)?(\d{2,5})\s*char(?:acter)?s", re.IGNORECASE),
    re.compile(r"\b0\s*/\s*(\d{2,5})\b"),
    re.compile(r"\(\s*(\d{2,5})\s*caracteres\s*\)", re.IGNORECASE),
)

_KIND_KEYWORDS: list[tuple[QuestionKind, tuple[str, ...]]] = [
    ("salary", ("pretens", "salari", "salary", "remunera", "compensation")),
    ("availability", ("disponibilidade", "quando voce pode", "quando você pode",
                      "data de inicio", "data de início", "start date", "availability",
                      "notice period", "aviso previo", "aviso prévio")),
    ("behavioral", ("situacao em que", "situação em que", "conte sobre uma vez",
                    "tell me about a time", "desafio que", "conflito", "feedback dificil",
                    "feedback difícil", "erro que voce cometeu", "erro que você cometeu")),
    ("motivation", ("por que", "por quê", "porque voce quer", "porque você quer",
                    "motivo", "interesse em trabalhar", "why do you want",
                    "why are you interested", "o que te atrai")),
    ("experience", ("experiencia", "experiência", "experience", "descreva sua",
                    "projetos que", "trajetoria", "trajetória", "background")),
    ("technical", ("como voce implementaria", "como você implementaria",
                   "explique o conceito", "diferenca entre", "diferença entre",
                   "o que e ", "o que é ", "how would you implement", "difference between")),
]

_OPTION_MARKERS = re.compile(r"^\s*(?:\(\s?\)|\[\s?\]|[○◯●◉•▢☐])\s*")

_JOB_SIGNAL_KEYWORDS = {
    "requirement": ("requisito", "qualifica", "requirement", "diferencia",
                    "o que buscamos", "what we're looking", "must have", "desejavel",
                    "desejável", "experiencia com", "experiência com"),
    "culture": ("cultura", "valores", "nossa missao", "nossa missão", "our values",
                "our culture", "beneficio", "benefício", "sobre a empresa", "about us"),
    "title": ("vaga", "job title", "cargo", "position", "estagio", "estágio",
              "junior", "júnior", "pleno", "senior", "sênior", "analista",
              "desenvolvedor", "engineer", "developer"),
}

_PLATFORM_HINTS = (
    ("gupy", ("gupy",)),
    ("linkedin", ("linkedin",)),
    ("greenhouse", ("greenhouse",)),
    ("lever", ("lever.co", "jobs.lever")),
    ("workday", ("workday", "myworkdayjobs")),
    ("indeed", ("indeed",)),
)


def _classify_kind(text: str) -> QuestionKind:
    lowered = text.lower()
    for kind, keywords in _KIND_KEYWORDS:
        if any(k in lowered for k in keywords):
            return kind
    return "open_text"


def _looks_like_question(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 12 or len(stripped) > 600:
        return False
    lowered = stripped.lower()
    if stripped.endswith("?"):
        return True
    if stripped.endswith(":") and any(lowered.startswith(s) for s in _QUESTION_STARTERS):
        return True
    return any(lowered.startswith(s) for s in _QUESTION_STARTERS) and len(stripped) > 20


def _find_char_limit(*texts: str) -> int | None:
    for text in texts:
        for pattern in _CHAR_LIMIT_PATTERNS:
            match = pattern.search(text)
            if match:
                return int(match.group(1))
    return None


def _collect_options(blocks: list, start_index: int) -> list[str] | None:
    options: list[str] = []
    for block in blocks[start_index + 1: start_index + 8]:
        text = block.text.strip()
        if _OPTION_MARKERS.match(text) and 0 < len(_OPTION_MARKERS.sub("", text)) <= 80:
            options.append(_OPTION_MARKERS.sub("", text).strip())
        elif options:
            break
    return options if len(options) >= 2 else None


def detect_platform(full_text: str, window_title: str | None) -> str | None:
    haystack = f"{full_text} {window_title or ''}".lower()
    for name, needles in _PLATFORM_HINTS:
        if any(n in haystack for n in needles):
            return name
    return None


def collect_job_signals(ocr: OcrResult) -> JobSignals:
    signals = JobSignals()
    for block in ocr.blocks:
        lowered = block.text.lower()
        if any(k in lowered for k in _JOB_SIGNAL_KEYWORDS["requirement"]):
            signals.requirement_snippets.append(block.text.strip())
        elif any(k in lowered for k in _JOB_SIGNAL_KEYWORDS["culture"]):
            signals.culture_snippets.append(block.text.strip())
        elif any(k in lowered for k in _JOB_SIGNAL_KEYWORDS["title"]):
            signals.title_snippets.append(block.text.strip())
    return signals


def analyze(ocr: OcrResult) -> ScreenAnalysis:
    questions: list[DetectedQuestion] = []
    blocks = sorted(ocr.blocks, key=lambda b: (b.bbox[1], b.bbox[0]))

    for index, block in enumerate(blocks):
        text = block.text.strip()
        if not _looks_like_question(text):
            continue
        neighbors = " ".join(b.text for b in blocks[index + 1: index + 3])
        options = _collect_options(blocks, index)
        kind = "multiple_choice" if options else _classify_kind(text)
        questions.append(
            DetectedQuestion(
                text=text.rstrip(":").strip(),
                kind=kind,
                char_limit=_find_char_limit(text, neighbors),
                options=options,
                confidence=0.9 if text.endswith("?") else 0.7,
            )
        )

    return ScreenAnalysis(
        questions=questions,
        job_signals=collect_job_signals(ocr),
        platform_hint=detect_platform(ocr.full_text, ocr.window_title),
    )


def is_ambiguous(analysis: ScreenAnalysis, ocr: OcrResult) -> bool:
    """Sem pergunta confiante mas com bastante texto na tela -> vale o fallback LLM."""
    if any(q.confidence >= 0.85 for q in analysis.questions):
        return False
    return len(ocr.full_text) > 200
