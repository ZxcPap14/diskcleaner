"""Тесты 4.15.0: история занятости дисков — снапшоты, тренд, прогноз."""
from __future__ import annotations

import datetime
from pathlib import Path

import disk_cleaner_app.services.disk_usage as disk_usage
from disk_cleaner_app.models.history import HistoryManager
from disk_cleaner_app.services.disk_usage import (
    forecast_free,
    forecast_text,
    record_snapshot,
    take_snapshot,
)


def _moments(count: int, step_days: float = 2.0) -> list[datetime.datetime]:
    base = datetime.datetime(2026, 1, 1, 12, 0, 0)
    return [base + datetime.timedelta(days=step_days * i) for i in range(count)]


def test_take_snapshot_uses_list_drives(monkeypatch) -> None:
    monkeypatch.setattr(
        disk_usage, "list_drives",
        lambda: [("C:\\", 10 * 1024 ** 3, 100 * 1024 ** 3)],
    )
    snapshot = take_snapshot()

    assert snapshot == [{
        "volume": "C:\\", "free": 10 * 1024 ** 3, "total": 100 * 1024 ** 3,
    }]


def test_record_snapshot_respects_interval(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        disk_usage, "list_drives",
        lambda: [("C:\\", 50 * 1024 ** 3, 100 * 1024 ** 3)],
    )
    history = HistoryManager(db_path=tmp_path / "history.db")
    moments = _moments(4, step_days=1.0)

    assert record_snapshot(history, now=moments[0]) == 1
    # Через час — слишком часто: не пишем.
    assert record_snapshot(
        history, now=moments[0] + datetime.timedelta(hours=1)
    ) == 0
    # Через сутки — пишем.
    assert record_snapshot(history, now=moments[1]) == 1


def test_usage_series_ordered_ascending(tmp_path: Path) -> None:
    history = HistoryManager(db_path=tmp_path / "history.db")
    moments = _moments(3)
    for index, moment in enumerate(moments):
        history.add_snapshots(
            [{"volume": "C:\\", "free": 90 - index, "total": 100}],
            moment,
        )

    series = history.usage_series("C:\\")

    assert [item["free"] for item in series] == [90, 89, 88]
    assert all(item["timestamp"] is not None for item in series)
    # Чужой том не попадает.
    assert history.usage_series("D:\\") == []


def test_forecast_needs_enough_points_and_span(tmp_path: Path) -> None:
    history = HistoryManager(db_path=tmp_path / "history.db")

    # 3 точки за 6 дней — мало точек.
    for index, moment in enumerate(_moments(3)):
        history.add_snapshots(
            [{"volume": "C:\\", "free": 90 - index, "total": 100}], moment
        )
    assert forecast_free(history.usage_series("C:\\")) is None

    # 4 точки за 1 день — мало времени наблюдений.
    base = datetime.datetime(2026, 1, 1, 12, 0, 0)
    for index in range(4):
        history.add_snapshots(
            [{"volume": "D:\\", "free": 90 - index, "total": 100}],
            base + datetime.timedelta(hours=index),
        )
    assert forecast_free(history.usage_series("D:\\")) is None


def test_forecast_predicts_exhaustion_date(tmp_path: Path) -> None:
    history = HistoryManager(db_path=tmp_path / "history.db")
    # Ровно −1 ГБ в сутки, начиная со 100 ГБ: порог 5 ГБ наступит
    # через 95 дней от последней точки.
    moments = _moments(8, step_days=3.0)
    for index, moment in enumerate(moments):
        free = (100 - index * 3) * 1024 ** 3
        history.add_snapshots(
            [{"volume": "C:\\", "free": free, "total": 120 * 1024 ** 3}],
            moment,
        )

    forecast = forecast_free(history.usage_series("C:\\"))

    assert forecast is not None
    assert forecast["slope_per_day"] < 0
    assert abs(forecast["slope_per_day"] + 1024 ** 3) < 1024 ** 2
    assert not forecast["already_low"]
    # 21 день наблюдений, свободно 79 ГБ, порог 6 ГБ → ~73 дня.
    assert 60 < forecast["days_left"] < 90
    assert forecast["date"] >= datetime.date.today().isoformat()


def test_forecast_refuses_growing_or_flat_space(tmp_path: Path) -> None:
    history = HistoryManager(db_path=tmp_path / "history.db")
    moments = _moments(6, step_days=3.0)
    for index, moment in enumerate(moments):
        free = (80 + index) * 1024 ** 3  # место растёт
        history.add_snapshots(
            [{"volume": "C:\\", "free": free, "total": 120 * 1024 ** 3}],
            moment,
        )
    assert forecast_free(history.usage_series("C:\\")) is None


def test_forecast_text_is_honest() -> None:
    no_data = forecast_text(None)
    assert "недостаточно" in no_data.lower() or "Прогноз появится" in no_data

    forecast = {
        "date": "2027-01-12", "days_left": 77.0,
        "slope_per_day": -(2 * 1024 ** 3), "points": 8,
        "span_days": 21.0, "already_low": False,
    }
    text = forecast_text(forecast)
    assert "2027-01-12" in text
    assert "2.00 ГБ/день" in text


def test_history_migration_creates_snapshots_table(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "history.db"
    # База старой версии: только таблица history.
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "CREATE TABLE history (id INTEGER PRIMARY KEY, date TEXT, "
            "items_cleaned INTEGER, bytes_freed INTEGER, details TEXT)"
        )

    history = HistoryManager(db_path=db)

    assert history.add_snapshots(
        [{"volume": "C:\\", "free": 1, "total": 2}]
    ) == 1
    assert history.usage_series("C:\\")[0]["total"] == 2


def test_add_operation_writes_snapshot(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        disk_usage, "list_drives",
        lambda: [("C:\\", 40 * 1024 ** 3, 100 * 1024 ** 3)],
    )
    history = HistoryManager(db_path=tmp_path / "history.db")

    history.add_operation([{"status": "OK"}], bytes_freed=1024, op_type="smart")

    assert history.usage_series("C:\\")


def test_insufficient_data_distinguishes_from_stable(tmp_path: Path) -> None:
    from disk_cleaner_app.services.disk_usage import insufficient_data

    history = HistoryManager(db_path=tmp_path / "history.db")
    # Мало точек.
    short = [
        {"date": "2026-01-01T12:00:00", "free": 1, "total": 100,
         "timestamp": 1_767_225_600.0},
    ]
    assert insufficient_data(short) is True

    # Достаточно точек и времени, место растёт — данных хватает,
    # просто прогноз не нужен.
    moments = _moments(6, step_days=3.0)
    for index, moment in enumerate(moments):
        history.add_snapshots(
            [{"volume": "C:\\", "free": (80 + index) * 1024 ** 3,
              "total": 120 * 1024 ** 3}],
            moment,
        )
    assert insufficient_data(history.usage_series("C:\\")) is False
    assert forecast_free(history.usage_series("C:\\")) is None
