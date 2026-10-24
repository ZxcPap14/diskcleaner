"""HistoryManager — SQLite история очисток (WAL + JSON details)."""
from __future__ import annotations

import datetime
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from disk_cleaner_app.models.config import CONFIG_DIR

log = logging.getLogger(__name__)

SCHEMA_VERSION = 2


class HistoryManager:
    """История очисток: SQLite с журналом WAL и устойчивой схемой."""

    def __init__(self, db_path: Path | None = None) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path or (CONFIG_DIR / "history.db")
        self._init_db()

    # ── соединение и схема ─────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.DatabaseError:
            # На сетевых/защищённых путях WAL недоступен — работаем как есть.
            pass
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    items_cleaned INTEGER,
                    bytes_freed INTEGER,
                    details TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_date ON history(date)"
            )
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    # ── запись ─────────────────────────────────────────

    def add(
        self,
        items_cleaned: int,
        bytes_freed: int,
        details: str = "",
        when: datetime.datetime | None = None,
    ) -> None:
        """Добавить запись. ``details`` — произвольная строка или JSON."""
        moment = (when or datetime.datetime.now()).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO history (date, items_cleaned, bytes_freed, details) "
                "VALUES (?, ?, ?, ?)",
                (moment, int(items_cleaned), int(bytes_freed), details),
            )

    def add_operation(self, results: list[dict], bytes_freed: int) -> None:
        """Сохранить операцию очистки в виде JSON-списка целей."""
        try:
            payload = json.dumps(results, ensure_ascii=False)
        except (TypeError, ValueError):
            payload = ""
        self.add(
            items_cleaned=sum(1 for r in results if r.get("status") == "OK"),
            bytes_freed=bytes_freed,
            details=payload,
        )

    # ── чтение ─────────────────────────────────────────

    def get_recent(self, limit: int = 20) -> list[tuple]:
        """Короткие строки (date, items, bytes) — для настроек/отчётов."""
        with self._connect() as conn:
            return conn.execute(
                "SELECT date, items_cleaned, bytes_freed FROM history "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def get_recent_full(self, limit: int = 20) -> list[dict]:
        """Полные записи с разобранным JSON в ``details``."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, date, items_cleaned, bytes_freed, details FROM history "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._to_dict(row) for row in rows]

    def get_all(self) -> list[dict]:
        """Все записи истории (новые сверху) — для отчётов."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, date, items_cleaned, bytes_freed, details FROM history "
                "ORDER BY id DESC"
            ).fetchall()
        return [self._to_dict(row) for row in rows]

    def get_last(self) -> dict | None:
        rows = self.get_recent_full(1)
        return rows[0] if rows else None

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM history").fetchone()
            return int(row[0]) if row else 0

    def total_freed(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(bytes_freed), 0) FROM history"
            ).fetchone()
            return int(row[0]) if row else 0

    # ── обслуживание ───────────────────────────────────

    def clear(self) -> None:
        """Удалить всю историю (используется настройками)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM history")

    def vacuum(self) -> None:
        with self._connect() as conn:
            conn.execute("VACUUM")

    # ── внутреннее ─────────────────────────────────────

    @staticmethod
    def _to_dict(row: tuple) -> dict[str, Any]:
        row_id, date, items, freed, details = row
        parsed: Any = None
        if details:
            try:
                parsed = json.loads(details)
            except (json.JSONDecodeError, TypeError):
                parsed = details
        return {
            "id": row_id,
            "date": date,
            "items_cleaned": items,
            "bytes_freed": freed,
            "details": parsed,
        }
