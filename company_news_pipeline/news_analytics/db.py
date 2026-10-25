"""SQLite access for the local anonymized-company analytics prototype."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


DEFAULT_DB_PATH = Path("data/news_analytics.sqlite3")


class Database:
    """Create short-lived SQLite connections and initialize the local schema."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured_path = path or os.getenv("NEWS_ANALYTICS_DB") or DEFAULT_DB_PATH
        self.path = Path(configured_path).expanduser()
        self._uri = str(configured_path) == ":memory:"
        self._dsn = (
            f"file:news_analytics_{id(self)}?mode=memory&cache=shared"
            if self._uri
            else str(self.path)
        )
        self._memory_keeper = (
            sqlite3.connect(self._dsn, uri=True, timeout=30.0) if self._uri else None
        )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a transactional connection with row access by column name."""

        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._dsn, timeout=30.0, uri=self._uri)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the schema idempotently without dropping existing records."""

        schema_path = Path(__file__).with_name("schema.sql")
        schema_sql = schema_path.read_text(encoding="utf-8")
        with self.connect() as connection:
            connection.executescript(schema_sql)


def get_database(path: str | Path | None = None) -> Database:
    """Build and initialize a database using an optional configured path."""

    database = Database(path)
    database.initialize()
    return database
