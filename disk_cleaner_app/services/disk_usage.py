"""📈 История занятости дисков: снапшоты, тренд и честный прогноз.

Снапшот — это (том, свободно, всего) в момент времени. Записывается
не чаще раза в 6 часов (изменение свободного места важнее частоты).
Прогноз строится линейной регрессией по последним точкам и показывается
только тогда, когда данных действительно достаточно; иначе — честное
«недостаточно данных».
"""
from __future__ import annotations

import datetime
import logging

from disk_cleaner_app.cleaners.base import list_drives
from disk_cleaner_app.models.history import HistoryManager

log = logging.getLogger(__name__)

# Минимальный интервал между снапшотами одного тома, часы.
SNAPSHOT_MIN_INTERVAL_HOURS = 6

# Прогноз честен только на достаточном протяжении наблюдений.
FORECAST_MIN_POINTS = 4
FORECAST_MIN_SPAN_DAYS = 7


def take_snapshot() -> list[dict]:
    """Текущая занятость всех готовых томов."""
    return [
        {"volume": root, "free": int(free), "total": int(total)}
        for root, free, total in list_drives()
    ]


def record_snapshot(
    history: HistoryManager,
    now: datetime.datetime | None = None,
    min_interval_hours: int = SNAPSHOT_MIN_INTERVAL_HOURS,
) -> int:
    """Записать снапшот, если давно не писали. Возвращает число записей."""
    moment = now or datetime.datetime.now()
    last = history.last_snapshot_time()
    if last is not None:
        elapsed = moment - last
        if elapsed < datetime.timedelta(hours=min_interval_hours):
            return 0
    return history.add_snapshots(take_snapshot(), moment)


def usage_series(history: HistoryManager, volume: str, limit: int = 90) -> list[dict]:
    """Точки занятости тома по возрастанию даты: [{date, free, total}]."""
    return history.usage_series(volume, limit=limit)


def forecast_free(
    series: list[dict],
    min_points: int = FORECAST_MIN_POINTS,
    min_span_days: float = FORECAST_MIN_SPAN_DAYS,
) -> dict | None:
    """Прогноз «место кончится к дате X» по тренду свободного места.

    Возвращает словарь с ``date`` (ГГГГ-ММ-ДД), ``days_left``,
    ``slope_per_day`` (байт в сутки, отрицательный), ``points``,
    ``span_days`` — или ``None``, если данных мало или место не
    убывает. Это оценка по тренду, а не обещание.
    """
    points = [
        (item["timestamp"], float(item["free"]))
        for item in series
        if item.get("timestamp") is not None
    ]
    if len(points) < min_points:
        return None

    span_seconds = points[-1][0] - points[0][0]
    if span_seconds <= 0:
        return None
    span_days = span_seconds / 86_400
    if span_days < min_span_days:
        return None

    # МНК по (t, free); t нормируем на сутки от первой точки.
    t0 = points[0][0]
    xs = [(t - t0) / 86_400 for t, _ in points]
    ys = [free for _, free in points]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator <= 0:
        return None
    slope = sum(
        (x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)
    ) / denominator

    latest_free = ys[-1]
    if slope >= 0:
        return None
    latest_total = int(series[-1].get("total") or 0)
    critical = latest_total * 0.05 if latest_total > 0 else 10 * 1024 ** 3
    margin = latest_free - critical
    if margin <= 0:
        # Порог уже пройден: «предсказывать» нечего, место кончилось.
        return {
            "date": datetime.datetime.now().date().isoformat(),
            "days_left": 0.0,
            "slope_per_day": slope,
            "points": n,
            "span_days": span_days,
            "already_low": True,
        }
    days_left = margin / (-slope)
    if days_left > 3650:
        # Тренд слишком пологий, чтобы обещать дату за горизонтом decade.
        return None
    forecast_date = datetime.datetime.now() + datetime.timedelta(days=days_left)
    return {
        "date": forecast_date.date().isoformat(),
        "days_left": days_left,
        "slope_per_day": slope,
        "points": n,
        "span_days": span_days,
        "already_low": False,
    }


def insufficient_data(series: list[dict]) -> bool:
    """True, если точек или времени наблюдений ещё слишком мало.

    Отличить это от «место не убывает» важно для честного текста
    вместо прогноза.
    """
    points = [
        item for item in series if item.get("timestamp") is not None
    ]
    if len(points) < FORECAST_MIN_POINTS:
        return True
    span_days = (points[-1]["timestamp"] - points[0]["timestamp"]) / 86_400
    return span_days < FORECAST_MIN_SPAN_DAYS


def forecast_text(forecast: dict | None) -> str:
    """Человеческая подпись прогноза для карточки."""
    if not forecast:
        return (
            "Прогноз появится, когда накопится история: "
            f"нужно ≥ {FORECAST_MIN_POINTS} точек за ≥ "
            f"{FORECAST_MIN_SPAN_DAYS:g} дней наблюдений."
        )
    slope_gb = abs(forecast["slope_per_day"]) / 1024 ** 3
    speed = (
        f"{slope_gb:.2f} ГБ/день"
        if slope_gb >= 0.01
        else f"{abs(forecast['slope_per_day']) / 1024 ** 2:.0f} МБ/день"
    )
    tail = f"тренд −{speed} по {forecast['points']} точкам за {forecast['span_days']:.0f} дн."
    if forecast.get("already_low"):
        return f"⚠️ Свободного места ниже порога ({tail})."
    return (
        f"По тренду место закончится к {forecast['date']} "
        f"(≈{forecast['days_left']:.0f} дн.; {tail})."
    )
