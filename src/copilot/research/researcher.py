"""Pesquisa de empresa: uma chamada ao Claude com a web search tool server-side,
seguida de estruturacao. Toda afirmacao carrega URL de fonte; claims sem fonte
sao descartados na validacao."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

from copilot.domain.models import CompanyProfile, JobContext
from copilot.llm.client import LlmClient
from copilot.storage.repository import Repository

_RESEARCH_SYSTEM = """Voce pesquisa informacoes PUBLICAS sobre uma empresa para ajudar um candidato
a personalizar respostas de candidatura.

Priorize fontes primarias: site oficial, pagina de carreiras/cultura, blog de engenharia,
imprensa reconhecida. Prefira conteudo recente e registre a data quando disponivel.

Ao final, responda APENAS com um JSON valido neste formato:
{
  "name": "...",
  "summary": "o que a empresa faz, mercado, porte (2-4 frases)",
  "products": ["..."],
  "tech_stack_public": ["tecnologias que a empresa cita publicamente"],
  "values_culture": [{"claim": "...", "source_url": "...", "source_date": "AAAA-MM ou null"}],
  "recent_news": [{"claim": "...", "source_url": "...", "source_date": "AAAA-MM ou null"}],
  "sources": ["urls consultadas"]
}
Toda entrada de values_culture e recent_news DEVE ter source_url. Sem fonte, nao inclua."""

_STRUCTURE_SYSTEM = """Converta o texto de pesquisa abaixo no schema pedido. Nao adicione informacao
nova; descarte afirmacoes de cultura/noticia sem URL de fonte."""


class CompanyResearcher:
    def __init__(self, llm: LlmClient, repository: Repository, ttl_days: int) -> None:
        self._llm = llm
        self._repository = repository
        self._ttl = timedelta(days=ttl_days)

    def get_profile(self, context: JobContext) -> tuple[CompanyProfile | None, bool]:
        """Retorna (perfil, veio_do_cache). None se nao ha empresa identificada."""
        if not context.company:
            return None, False
        key = (context.company_domain or context.company).lower().strip()

        cached = self._repository.get_company_cache(key)
        if cached is not None:
            age = datetime.now(UTC) - cached.researched_at
            if age < self._ttl:
                return cached, True

        profile = self._research(context)
        if profile is not None:
            self._repository.set_company_cache(key, profile)
        return profile, False

    def _research(self, context: JobContext) -> CompanyProfile | None:
        hints = []
        if context.company_domain:
            hints.append(f"dominio: {context.company_domain}")
        if context.role_title:
            hints.append(f"a vaga e de: {context.role_title}")
        if context.technologies:
            hints.append(f"tecnologias da vaga: {', '.join(context.technologies[:8])}")
        user = (
            f"Pesquise a empresa: {context.company}\n"
            + ("\n".join(hints) + "\n" if hints else "")
            + "Foque em: o que faz, produtos, cultura/valores, stack publica, noticias recentes."
        )
        raw = self._llm.research(system=_RESEARCH_SYSTEM, user=user)
        profile = self._parse_json(raw)
        if profile is not None:
            return profile
        # Fallback: estruturacao com o modelo leve quando o JSON veio malformado
        return self._llm.extract(
            system=_STRUCTURE_SYSTEM,
            user=raw,
            schema=CompanyProfile,
            purpose="research_structuring",
        )

    @staticmethod
    def _parse_json(raw: str) -> CompanyProfile | None:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            data.setdefault("name", "")
            profile = CompanyProfile.model_validate(data)
            return profile if profile.name else None
        except Exception:
            return None


def relevant_slice(profile: CompanyProfile, question_kind: str) -> str:
    """Recorte do CompanyProfile para o prompt de geracao: cultura sempre;
    produtos/stack so quando a pergunta pede; noticias so recentes."""
    lines = [f"Empresa: {profile.name}", profile.summary]
    if profile.values_culture:
        lines.append("Cultura/valores (com fonte):")
        lines += [f"- {c.claim} [{c.source_url}]" for c in profile.values_culture[:6]]
    if question_kind in ("motivation", "technical", "experience", "open_text"):
        if profile.products:
            lines.append("Produtos: " + ", ".join(profile.products[:6]))
        if profile.tech_stack_public:
            lines.append("Stack publica: " + ", ".join(profile.tech_stack_public[:10]))
    fresh_news = [n for n in profile.recent_news if not _is_stale(n.source_date)][:3]
    if fresh_news and question_kind in ("motivation", "open_text"):
        lines.append("Noticias recentes (com fonte):")
        lines += [f"- {n.claim} [{n.source_url}]" for n in fresh_news]
    return "\n".join(line for line in lines if line)


def _is_stale(source_date: str | None, months: int = 18) -> bool:
    if not source_date:
        return False
    try:
        year, month = (int(p) for p in source_date.split("-")[:2])
        age_months = (datetime.now(UTC).year - year) * 12 \
            + datetime.now(UTC).month - month
        return age_months > months
    except Exception:
        return False
