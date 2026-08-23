"""Executable in-memory SQLite adapter for the demo profile."""

from __future__ import annotations

from typing import Any

from sqlit.domains.connections.providers.sqlite.adapter import SQLiteAdapter


class SQLiteDemoAdapter(SQLiteAdapter):
    """SQLite demo data backed by a real in-memory SQL engine."""

    def __init__(self) -> None:
        self._query_delay = 0.0

    def connect(self, config: Any) -> Any:
        import sqlite3

        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO users VALUES
                (1, 'Alice Johnson', 'alice@example.com', '2024-01-15'),
                (2, 'Bob Smith', 'bob@example.com', '2024-01-16'),
                (3, 'Charlie Brown', 'charlie@example.com', '2024-01-17');

            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL
            );
            INSERT INTO products VALUES
                (1, 'Widget', 9.99, 100),
                (2, 'Gadget', 19.99, 50),
                (3, 'Gizmo', 29.99, 25);

            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                product_id INTEGER NOT NULL REFERENCES products(id),
                quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO orders VALUES
                (1, 1, 1, 2, '2024-01-20'),
                (2, 1, 2, 1, '2024-01-21'),
                (3, 2, 3, 3, '2024-01-22');
            """
        )
        return conn

    def execute_query(
        self, conn: Any, query: str, max_rows: int | None = None
    ) -> tuple[list[str], list[tuple], bool]:
        if self._query_delay > 0:
            import time

            time.sleep(self._query_delay)
        return super().execute_query(conn, query, max_rows)

    def apply_query_delay(self, delay: float) -> None:
        self._query_delay = delay

    def apply_demo_options(
        self, demo_rows: int = 0, demo_long_text: bool = False
    ) -> None:
        """Keep the executable dataset stable for the SQLite demo."""
