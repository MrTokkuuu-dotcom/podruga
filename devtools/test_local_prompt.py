"""Проверка подсказки для своего мозга. Запуск: ~/Podruga/venv/bin/python devtools/test_local_prompt.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from local_prompt import LOCAL_RULES, stable_system, turn_text  # noqa: E402

a = stable_system("Ты Аня.", "- Мягкая.", "- Живёт в Пусане.", "Дима")
b = stable_system("Ты Аня.", "- Мягкая.", "- Живёт в Пусане.", "Дима")
assert a == b, "стабильная часть должна быть одинаковой"
assert "2026" not in a and "## Сейчас" not in a, "в стабильной части не должно быть времени"
assert "Пусане" in a and "Дима" in a and "{user}" not in a
assert "[[" not in LOCAL_RULES, "свой мозг получает уже расшифрованную речь"
for cmd in ("НАПОМНИТЬ", "ТАЙМЕР", "ОТКРЫТЬ", "МУЗЫКА", "ГРОМКОСТЬ", "ПОИСК", "ПОКАЗАТЬ", "ГУЛЯТЬ", "РЕЖИМ", "<МОЛЧУ>"):
    assert cmd in LOCAL_RULES, cmd

fresh = "## Сейчас\nвоскресенье, 23.11.2026 21:40"
en = turn_text("How was your day?", "en", fresh)
ko = turn_text("오늘 뭐 먹을까?", "ko", fresh)
ru = turn_text("привет", "ru", fresh)
assert "ПО-АНГЛИЙСКИ" in en and en.endswith("How was your day?") and en.startswith("## Сейчас")
assert "ПО-КОРЕЙСКИ" in ko and "반말" in ko
assert "ПО-АНГЛИЙСКИ" not in ru and "ПО-КОРЕЙСКИ" not in ru and ru.endswith("привет")
assert turn_text("hi", "en", "").startswith("(Он сказал"), "без свежей части — сразу приписка"
print("OK")
