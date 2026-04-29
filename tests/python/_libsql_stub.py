"""
Minimal libsql_client stub backed by Python's built-in sqlite3.
Injected via sys.modules in conftest.py so worker.db can be imported and
tested locally without the real libsql-client package installed.

Mirrors the subset of the libsql_client API used by worker/db.py:
  - Statement(sql, params)
  - create_client(url, auth_token="")  -> Client
  - await client.execute(stmt)         -> ResultSet(.rows, .columns, .rows_affected)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


class Statement:
    def __init__(self, sql: str, params=None):
        self.sql = sql
        self.params = params or []


class ResultSet:
    def __init__(self, rows: list, columns: list[str], rows_affected: int):
        self.rows = rows
        self.columns = columns
        self.rows_affected = rows_affected


class Client:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.commit()

    async def execute(self, stmt: Statement | str, params=None) -> ResultSet:
        if isinstance(stmt, str):
            stmt = Statement(stmt, params)
        cursor = self._conn.execute(stmt.sql, stmt.params)
        self._conn.commit()
        columns = [d[0] for d in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        rows_affected = max(cursor.rowcount, 0)
        return ResultSet(rows, columns, rows_affected)

    async def close(self) -> None:
        self._conn.close()


def create_client(url: str, auth_token: str = "") -> Client:
    path = url[len("file:"):] if url.startswith("file:") else ":memory:"
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    return Client(path)
