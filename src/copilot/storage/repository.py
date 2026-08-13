from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from copilot.domain.models import (
    AnswerBundle,
    CompanyProfile,
    DetectedQuestion,
    JobContext,
)
from copilot.storage.models import (
    AnswerRow,
    ApplicationRow,
    CompanyCacheRow,
    QuestionRow,
)


@dataclass
class SearchHit:
    answer_id: int
    question_text: str
    answer_text: str
    company: str
    role: str


class Repository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sessions = session_factory
        self._fts_available: bool | None = None

    # ------------------------------------------------------------ applications

    def upsert_application(self, context: JobContext) -> int:
        company = (context.company or "").strip()
        role = (context.role_title or "").strip()
        with self._sessions() as session:
            row = session.execute(
                select(ApplicationRow).where(
                    ApplicationRow.company == company,
                    ApplicationRow.role_title == role,
                )
            ).scalar_one_or_none()
            if row is None:
                row = ApplicationRow(company=company, role_title=role)
                session.add(row)
            row.job_context_json = context.model_dump_json()
            session.commit()
            return row.id

    def get_job_context(self, company: str | None, role: str | None) -> JobContext | None:
        with self._sessions() as session:
            row = session.execute(
                select(ApplicationRow).where(
                    ApplicationRow.company == (company or "").strip(),
                    ApplicationRow.role_title == (role or "").strip(),
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return JobContext.model_validate_json(row.job_context_json)

    def list_applications(self) -> list[ApplicationRow]:
        with self._sessions() as session:
            return list(
                session.execute(
                    select(ApplicationRow).order_by(ApplicationRow.updated_at.desc())
                ).scalars()
            )

    # ------------------------------------------------- questions / answers

    def save_question(self, application_id: int, question: DetectedQuestion) -> int:
        with self._sessions() as session:
            existing = session.execute(
                select(QuestionRow).where(
                    QuestionRow.application_id == application_id,
                    QuestionRow.text == question.text,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing.id
            row = QuestionRow(
                application_id=application_id,
                text=question.text,
                kind=question.kind,
                char_limit=question.char_limit,
            )
            session.add(row)
            session.commit()
            return row.id

    def save_answer(self, question_id: int, bundle: AnswerBundle) -> int:
        with self._sessions() as session:
            row = AnswerRow(
                question_id=question_id,
                suggested_text=bundle.suggestion.answer,
                rationale=bundle.suggestion.rationale,
                facts_used_json=json.dumps(bundle.suggestion.facts_used),
                caveats_json=json.dumps(bundle.suggestion.caveats, ensure_ascii=False),
                verification_json=bundle.verification.model_dump_json(),
                cost_usd=bundle.cost_usd,
            )
            session.add(row)
            session.commit()
            question = session.get(QuestionRow, question_id)
            application = session.get(ApplicationRow, question.application_id)
            self._fts_index(
                session, row.id, question.text, bundle.suggestion.answer,
                application.company, application.role_title,
            )
            session.commit()
            return row.id

    def update_final_answer(self, answer_id: int, final_text: str) -> None:
        with self._sessions() as session:
            row = session.get(AnswerRow, answer_id)
            if row is not None:
                row.final_text = final_text
                session.commit()

    def approved_examples(self, limit: int = 3) -> list[str]:
        """Respostas que o usuario editou/aprovou — viram few-shot de estilo."""
        with self._sessions() as session:
            rows = session.execute(
                select(AnswerRow)
                .where(AnswerRow.final_text.is_not(None))
                .order_by(AnswerRow.created_at.desc())
                .limit(limit)
            ).scalars()
            return [r.final_text for r in rows if r.final_text]

    # ------------------------------------------------------------------ busca

    def _fts_index(self, session, answer_id: int, question_text: str,
                   answer_text: str, company: str, role: str) -> None:
        if self._check_fts(session):
            session.execute(
                text(
                    "INSERT INTO answers_fts(rowid, question_text, answer_text, company, role) "
                    "VALUES (:rid, :q, :a, :c, :r)"
                ),
                {"rid": answer_id, "q": question_text, "a": answer_text,
                 "c": company, "r": role},
            )

    def _check_fts(self, session) -> bool:
        if self._fts_available is None:
            try:
                session.execute(text("SELECT count(*) FROM answers_fts"))
                self._fts_available = True
            except Exception:
                self._fts_available = False
        return self._fts_available

    def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        with self._sessions() as session:
            if self._check_fts(session) and query.strip():
                rows = session.execute(
                    text(
                        "SELECT rowid, question_text, answer_text, company, role "
                        "FROM answers_fts WHERE answers_fts MATCH :q LIMIT :n"
                    ),
                    {"q": query, "n": limit},
                ).all()
                return [SearchHit(*row) for row in rows]
            like = f"%{query}%"
            rows = session.execute(
                select(AnswerRow, QuestionRow, ApplicationRow)
                .join(QuestionRow, AnswerRow.question_id == QuestionRow.id)
                .join(ApplicationRow, QuestionRow.application_id == ApplicationRow.id)
                .where(
                    QuestionRow.text.like(like) | AnswerRow.suggested_text.like(like)
                )
                .limit(limit)
            ).all()
            return [
                SearchHit(a.id, q.text, a.suggested_text, app.company, app.role_title)
                for a, q, app in rows
            ]

    # -------------------------------------------------------------- cache

    def get_company_cache(self, key: str) -> CompanyProfile | None:
        with self._sessions() as session:
            row = session.get(CompanyCacheRow, key)
            if row is None:
                return None
            profile = CompanyProfile.model_validate_json(row.profile_json)
            researched = row.researched_at
            if researched.tzinfo is None:
                researched = researched.replace(tzinfo=UTC)
            profile.researched_at = researched
            return profile

    def set_company_cache(self, key: str, profile: CompanyProfile) -> None:
        with self._sessions() as session:
            row = session.get(CompanyCacheRow, key)
            if row is None:
                row = CompanyCacheRow(key=key, profile_json=profile.model_dump_json())
                session.add(row)
            else:
                row.profile_json = profile.model_dump_json()
            row.researched_at = datetime.now(UTC)
            session.commit()

    # ------------------------------------------------------------- limpeza

    def delete_application(self, application_id: int) -> None:
        with self._sessions() as session:
            row = session.get(ApplicationRow, application_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def delete_all(self) -> None:
        with self._sessions() as session:
            for model in (AnswerRow, QuestionRow, ApplicationRow, CompanyCacheRow):
                for row in session.execute(select(model)).scalars():
                    session.delete(row)
            if self._check_fts(session):
                session.execute(text("DELETE FROM answers_fts"))
            session.commit()
