from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "candidate-copilot"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COPILOT_", env_file=".env", extra="ignore")

    data_dir: Path = default_data_dir()
    profile_path: Path | None = None

    hotkey_analyze: str = "<ctrl>+<shift>+<space>"
    hotkey_kill: str = "<ctrl>+<shift>+<esc>"

    model_generation: str = "claude-opus-5"
    model_light: str = "claude-haiku-4-5"

    research_ttl_days: int = 7
    research_max_searches: int = 8
    monthly_budget_usd: float = 20.0

    ocr_min_confidence: float = 0.4
    screen_diff_threshold: int = 6  # distancia de hamming abaixo da qual reusa o OCR

    redact_before_send: bool = True
    language: str = "pt-BR"

    # Padroes que marcam uma janela como "contexto de candidatura" (filtro de escopo)
    scope_patterns: list[str] = [
        "linkedin", "gupy", "greenhouse", "lever", "workday", "myworkdayjobs",
        "indeed", "vagas", "vaga", "careers", "carreiras", "jobs", "trabalhe conosco",
        "glassdoor", "catho", "infojobs", "programathor", "remotar",
    ]

    @property
    def db_path(self) -> Path:
        return self.data_dir / "copilot.db"

    def resolved_profile_path(self) -> Path:
        if self.profile_path:
            return self.profile_path
        local = Path("profile.yaml")
        if local.exists():
            return local
        return self.data_dir / "profile.yaml"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
