"""Wrapper unico do SDK anthropic: escolha de modelo por tarefa, prompt caching,
structured outputs, tratamento de recusa e contagem de custo local.

Toda chamada externa do app passa por esta classe — e o payload ja deve chegar
aqui redigido (privacy.redactor).
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel

from copilot.config import Settings

KEYRING_SERVICE = "candidate-copilot"
KEYRING_ENTRY = "anthropic_api_key"

# USD por token (precos por MTok / 1e6). Cache: leitura ~0.1x, escrita ~1.25x.
_PRICES: dict[str, dict[str, float]] = {
    "claude-opus-5": {"in": 5e-6, "out": 25e-6},
    "claude-haiku-4-5": {"in": 1e-6, "out": 5e-6},
}
_WEB_SEARCH_PRICE = 0.01  # ~US$10 / 1000 buscas

T = TypeVar("T", bound=BaseModel)


class MissingApiKeyError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "Chave da Claude API nao configurada. Defina ANTHROPIC_API_KEY ou rode "
            "`copilot --set-api-key` para guarda-la no keyring do sistema."
        )


class LlmRefusalError(RuntimeError):
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or "O modelo recusou esta solicitacao.")


@dataclass
class CostRecord:
    model: str
    purpose: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    searches: int = 0

    @property
    def usd(self) -> float:
        prices = _PRICES.get(self.model, {"in": 5e-6, "out": 25e-6})
        return (
            self.input_tokens * prices["in"]
            + self.output_tokens * prices["out"]
            + self.cache_read_tokens * prices["in"] * 0.1
            + self.cache_write_tokens * prices["in"] * 1.25
            + self.searches * _WEB_SEARCH_PRICE
        )


@dataclass
class CostTracker:
    records: list[CostRecord] = field(default_factory=list)

    def add(self, record: CostRecord) -> None:
        self.records.append(record)

    @property
    def total_usd(self) -> float:
        return sum(r.usd for r in self.records)

    def since(self, index: int) -> float:
        return sum(r.usd for r in self.records[index:])


def resolve_api_key() -> str | None:
    """None => o SDK resolve sozinho pelo ambiente (env var / perfil `ant`)."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return None
    try:
        import keyring

        stored = keyring.get_password(KEYRING_SERVICE, KEYRING_ENTRY)
        if stored:
            return stored
    except Exception:
        pass
    return None


def store_api_key(key: str) -> None:
    import keyring

    keyring.set_password(KEYRING_SERVICE, KEYRING_ENTRY, key)


class LlmClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None
        self._lock = threading.Lock()
        self.costs = CostTracker()

    def _get_client(self):
        with self._lock:
            if self._client is None:
                import anthropic

                key = resolve_api_key()
                try:
                    self._client = (
                        anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
                    )
                except anthropic.AnthropicError as exc:
                    raise MissingApiKeyError() from exc
            return self._client

    def _record(self, model: str, purpose: str, usage, searches: int = 0) -> CostRecord:
        record = CostRecord(
            model=model,
            purpose=purpose,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            searches=searches,
        )
        self.costs.add(record)
        return record

    @staticmethod
    def _check_refusal(response) -> None:
        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            explanation = getattr(details, "explanation", None) if details else None
            raise LlmRefusalError(explanation)

    # ------------------------------------------------------------- operacoes

    def extract(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        purpose: str = "extract",
        max_tokens: int = 2048,
    ) -> T:
        """Classificacao/extracao estruturada com o modelo leve (Haiku)."""
        client = self._get_client()
        response = client.messages.parse(
            model=self._settings.model_light,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        self._check_refusal(response)
        self._record(self._settings.model_light, purpose, response.usage)
        if response.parsed_output is None:
            raise RuntimeError(f"Saida do modelo nao validou contra {schema.__name__}")
        return response.parsed_output

    def generate(
        self,
        *,
        cached_system: str,
        user: str,
        schema: type[T],
        purpose: str = "generate",
        max_tokens: int = 16000,
    ) -> T:
        """Geracao com o modelo forte (Opus 5). O system prompt (regras + perfil)
        e estavel entre chamadas e leva cache_control."""
        client = self._get_client()
        response = client.messages.parse(
            model=self._settings.model_generation,
            max_tokens=max_tokens,
            system=[{
                "type": "text",
                "text": cached_system,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        self._check_refusal(response)
        self._record(self._settings.model_generation, purpose, response.usage)
        if response.parsed_output is None:
            raise RuntimeError(f"Saida do modelo nao validou contra {schema.__name__}")
        return response.parsed_output

    def research(self, *, system: str, user: str, purpose: str = "research") -> str:
        """Chamada com a web search tool server-side; devolve o texto final.
        Trata pause_turn (loop do servidor) re-enviando a conversa."""
        client = self._get_client()
        model = self._settings.model_generation
        messages: list[dict] = [{"role": "user", "content": user}]
        tools = [{
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": self._settings.research_max_searches,
        }]

        response = None
        for _ in range(4):
            response = client.messages.create(
                model=model,
                max_tokens=8000,
                system=system,
                messages=messages,
                tools=tools,
            )
            searches = sum(
                1 for block in response.content
                if getattr(block, "type", "") == "server_tool_use"
            )
            self._record(model, purpose, response.usage, searches=searches)
            self._check_refusal(response)
            if response.stop_reason != "pause_turn":
                break
            messages = [
                {"role": "user", "content": user},
                {"role": "assistant", "content": response.content},
            ]

        parts = [
            block.text for block in response.content
            if getattr(block, "type", "") == "text"
        ]
        return "\n".join(parts)
