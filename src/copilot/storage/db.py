from __future__ import annotations

import contextlib
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from copilot.storage.models import Base

_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS answers_fts USING fts5(
    question_text, answer_text, company, role
)
"""


def create_db(path: Path | str) -> tuple[Engine, sessionmaker]:
    url = "sqlite:///:memory:" if str(path) == ":memory:" else f"sqlite:///{path}"
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    Base.metadata.create_all(engine)
    # Build de SQLite sem FTS5: a busca cai para LIKE no repository
    with contextlib.suppress(Exception), engine.begin() as connection:
        connection.execute(text(_FTS_DDL))
    return engine, sessionmaker(bind=engine, expire_on_commit=False, future=True)
