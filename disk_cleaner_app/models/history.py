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

SCHEMA_VERSION = 4

# Понятные имена типов операций (для фильтра в UI).
OP_TYPES = ("smart", "deep", "clean")
OP_TYPE_LABELS = {
    "smart": "Smart Clean",
    "deep": "Глубокая очистка",
    "clean": "Очистка",
}


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
                    details TEXT,
                    op_type TEXT DEFAULT 'clean'
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_date ON history(date)"
            )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS disk_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    volume TEXT,
                    free_bytes INTEGER,
                    total_bytes INTEGER
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_volume_date "
                "ON disk_snapshots(volume, date)"
            )
            self._migrate(conn)
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Добавить op_type в базы старых версий (v2 без колонки)."""
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(history)")
        }
        if "op_type" not in columns:
            conn.execute(
                "ALTER TABLE history ADD COLUMN op_type TEXT DEFAULT 'clean'"
            )

    # ── запись ─────────────────────────────────────────

    def add(
        self,
        items_cleaned: int,
        bytes_freed: int,
        details: str = "",
        when: datetime.datetime | None = None,
        op_type: str = "clean",
    ) -> None:
        """Добавить запись. ``details`` — произвольная строка или JSON."""
        moment = (when or datetime.datetime.now()).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO history (date, items_cleaned, bytes_freed, details, "
                "op_type) VALUES (?, ?, ?, ?, ?)",
                (moment, int(items_cleaned), int(bytes_freed), details, op_type),
            )

    def add_operation(
        self, results: list[dict], bytes_freed: int, op_type: str = "clean"
    ) -> None:
        """Сохранить операцию очистки в виде JSON-списка целей.

        Вместе с операцией пишется снапшот занятости томов (не чаще раза
        в 6 часов): «освобождено» подтверждается замером, а тренд места
        собирается сам.
        """
        try:
            payload = json.dumps(results, ensure_ascii=False)
        except (TypeError, ValueError):
            payload = ""
        self.add(
            items_cleaned=sum(1 for r in results if r.get("status") == "OK"),
            bytes_freed=bytes_freed,
            details=payload,
            op_type=op_type,
        )
        try:
            from disk_cleaner_app.services.disk_usage import record_snapshot

            record_snapshot(self)
        except Exception:
            log.debug("Снапшот занятости не удался", exc_info=True)

    # ── снапшоты занятости томов ───────────────────────

    def add_snapshots(
        self, items: list[dict], when: datetime.datetime | None = None
    ) -> int:
        """Записать снапшоты томов одним моментом. → сколько записано."""
        moment = (when or datetime.datetime.now()).isoformat()
        rows = [
            (moment, str(item["volume"]), int(item["free"]), int(item["total"]))
            for item in items
        ]
        if not rows:
            return 0
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO disk_snapshots (date, volume, free_bytes, "
                "total_bytes) VALUES (?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def last_snapshot_time(self) -> datetime.datetime | None:
        """Момент самого свежего снапшота или None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT date FROM disk_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row or not row[0]:
            return None
        try:
            return datetime.datetime.fromisoformat(str(row[0]))
        except ValueError:
            return None

    def usage_series(self, volume: str, limit: int = 90) -> list[dict]:
        """Точки занятости тома по возрастанию даты.

        Каждый элемент: ``date`` (ISO), ``free``, ``total`` и
        ``timestamp`` (epoch, для регрессии).
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT date, free_bytes, total_bytes FROM disk_snapshots "
                "WHERE volume = ? ORDER BY id DESC LIMIT ?",
                (str(volume), int(limit)),
            ).fetchall()
        series: list[dict] = []
        for date_text, free, total in reversed(rows):
            timestamp: float | None = None
            try:
                timestamp = datetime.datetime.fromisoformat(
                    str(date_text)
                ).timestamp()
            except ValueError:
                pass
            series.append({
                "date": str(date_text),
                "free": int(free),
                "total": int(total),
                "timestamp": timestamp,
            })
        return series

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
                "SELECT id, date, items_cleaned, bytes_freed, details, op_type "
                "FROM history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._to_dict(row) for row in rows]

    def get_all(self) -> list[dict]:
        """Все записи истории (новые сверху) — для отчётов."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, date, items_cleaned, bytes_freed, details, op_type "
                "FROM history ORDER BY id DESC"
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
        row_id, date, items, freed, details, op_type = row
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
            "op_type": op_type or "clean",
        }
