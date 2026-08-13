from __future__ import annotations

import pytest

from copilot.domain.models import OcrBlock, OcrResult
from copilot.domain.profile import UserProfile


def make_ocr(lines: list[str], *, start_y: float = 10.0, line_height: float = 30.0) -> OcrResult:
    blocks = [
        OcrBlock(
            text=line,
            bbox=(10.0, start_y + i * line_height, 600.0, start_y + i * line_height + 20.0),
            confidence=0.95,
        )
        for i, line in enumerate(lines)
    ]
    return OcrResult(blocks=blocks, full_text="\n".join(lines))


@pytest.fixture
def sample_profile() -> UserProfile:
    return UserProfile.model_validate({
        "identity": {"name": "Ana Dev", "headline": "Backend Python"},
        "experiences": [
            {
                "id": "exp-001",
                "company": "Empresa X",
                "role": "Desenvolvedora Backend",
                "period": "2022-2024",
                "facts": [
                    "Mantive APIs REST em Python/FastAPI com 200k req/dia",
                    "Reduzi p95 de 800ms para 220ms",
                ],
                "skills": ["python", "fastapi", "postgres"],
            }
        ],
        "projects": [
            {"id": "proj-001", "name": "Copilot", "facts": ["Assistente local"],
             "skills": ["python", "sqlite"]}
        ],
        "skills_matrix": {
            "python": {"level": "avancado", "years": 4},
            "fastapi": {"level": "intermediario", "years": 2},
        },
        "constraints": ["Nunca inventar experiencia"],
    })
