from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import sqlite3


@dataclass(frozen=True)
class DatabaseSettings:
    url: str = "sqlite:///data/phigraph.db"

    @property
    def sqlite_path(self) -> str:
        prefix = "sqlite:///"
        if not self.url.startswith(prefix):
            raise ValueError(
                "Built-in runtime supports sqlite URLs directly. "
                "PostgreSQL URLs are deployment configuration targets."
            )
        return self.url[len(prefix):]


class Database:
    def __init__(self, settings: DatabaseSettings):
        self.settings = settings

    @contextmanager
    def connect(self):
        path = self.settings.sqlite_path
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
