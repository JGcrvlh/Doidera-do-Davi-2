from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator


class Experience(BaseModel):
    id: str
    company: str
    role: str
    period: str = ""
    facts: list[str] = []
    skills: list[str] = []


class Project(BaseModel):
    id: str
    name: str
    facts: list[str] = []
    skills: list[str] = []


class Education(BaseModel):
    id: str
    institution: str
    degree: str = ""
    period: str = ""


class SkillEntry(BaseModel):
    level: str = "iniciante"
    years: float = 0.0


class Preferences(BaseModel):
    tone: str = "profissional, direto, primeira pessoa"
    language: str = "pt-BR"


class Identity(BaseModel):
    name: str = ""
    headline: str = ""
    location: str = ""


class UserProfile(BaseModel):
    identity: Identity = Identity()
    experiences: list[Experience] = []
    projects: list[Project] = []
    education: list[Education] = []
    skills_matrix: dict[str, SkillEntry] = {}
    constraints: list[str] = []
    preferences: Preferences = Preferences()

    @field_validator("skills_matrix", mode="before")
    @classmethod
    def _normalize_skill_keys(cls, value: dict) -> dict:
        return {str(k).strip().lower(): v for k, v in (value or {}).items()}

    def all_fact_ids(self) -> set[str]:
        ids = {e.id for e in self.experiences}
        ids |= {p.id for p in self.projects}
        ids |= {e.id for e in self.education}
        return ids

    def known_technologies(self) -> set[str]:
        techs = {t.lower() for t in self.skills_matrix}
        for exp in self.experiences:
            techs |= {s.lower() for s in exp.skills}
        for proj in self.projects:
            techs |= {s.lower() for s in proj.skills}
        return techs

    def facts_by_id(self) -> dict[str, list[str]]:
        table: dict[str, list[str]] = {}
        for exp in self.experiences:
            table[exp.id] = [f"{exp.role} @ {exp.company} ({exp.period})", *exp.facts]
        for proj in self.projects:
            table[proj.id] = [f"Projeto: {proj.name}", *proj.facts]
        for edu in self.education:
            table[edu.id] = [f"{edu.degree} — {edu.institution} ({edu.period})"]
        return table

    def render_for_prompt(self) -> str:
        """Renderizacao estavel do perfil (mesma string em toda chamada, para
        aproveitar o prompt caching)."""
        lines: list[str] = []
        if self.identity.name:
            lines.append(f"Candidato: {self.identity.name} — {self.identity.headline}")
        lines.append("\n## Experiencias")
        for e in self.experiences:
            lines.append(f"[{e.id}] {e.role} @ {e.company} ({e.period})")
            lines.extend(f"  - {fact}" for fact in e.facts)
            if e.skills:
                lines.append(f"  skills: {', '.join(e.skills)}")
        lines.append("\n## Projetos")
        for p in self.projects:
            lines.append(f"[{p.id}] {p.name}")
            lines.extend(f"  - {fact}" for fact in p.facts)
        if self.education:
            lines.append("\n## Formacao")
            for ed in self.education:
                lines.append(f"[{ed.id}] {ed.degree} — {ed.institution} ({ed.period})")
        lines.append("\n## Skills (nivel declarado — NUNCA elevar)")
        for name, entry in sorted(self.skills_matrix.items()):
            lines.append(f"- {name}: {entry.level} ({entry.years} anos)")
        if self.constraints:
            lines.append("\n## Restricoes do candidato")
            lines.extend(f"- {c}" for c in self.constraints)
        return "\n".join(lines)


class ProfileError(RuntimeError):
    pass


def load_profile(path: Path) -> UserProfile:
    if not path.exists():
        raise ProfileError(
            f"Perfil nao encontrado em {path}. Copie profile.example.yaml para "
            "profile.yaml e preencha com seus dados reais."
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profile = UserProfile.model_validate(data)
    ids = [e.id for e in profile.experiences] + [p.id for p in profile.projects] \
        + [e.id for e in profile.education]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ProfileError(f"IDs duplicados no perfil: {sorted(duplicates)}")
    return profile
