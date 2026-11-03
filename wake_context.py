"""Текст, который она получает при «пробуждении»: что было и сколько её не было.
Собирается программой, без ИИ — бесплатно и точно."""
from datetime import datetime

from journal import Journal, format_duration, now

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

REASONS = {
    "start": "программа только что запустилась",
    "game": "закончилась игра",
    "gpu": "видеокарта освободилась",
    "hotkey": "пауза снята вручную",
}


def away_hint(away_sec: float, now_dt: datetime, since_dt: datetime | None) -> str:
    if since_dt and since_dt.date() < now_dt.date() and 5 <= now_dt.hour < 13:
        return "Скорее всего, он только проснулся — поздоровайся по-утреннему."
    if away_sec < 30 * 60:
        return "Его не было недолго — просто тепло отметь, что рада снова его слышать."
    if away_sec < 3 * 3600:
        return "Обычный перерыв."
    return "Его не было долго — скажи, что скучала, и мягко спроси, как он."


def build_wake_context(journal: Journal, reason: str, away_sec: float,
                       since_dt: datetime | None = None, limit: int = 10) -> str:
    n = now()
    lines = [
        f"Сейчас {WEEKDAYS[n.weekday()]}, {n.strftime('%d.%m %H:%M')}.",
        f"Почему ты снова здесь: {REASONS.get(reason, reason)}.",
        f"Тебя не было: {format_duration(away_sec)}.",
        f"Подсказка: {away_hint(away_sec, n, since_dt)}",
        "",
        "Последние события:",
        journal.render(limit) or "(журнал пуст)",
    ]
    return "\n".join(lines)
