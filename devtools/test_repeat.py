"""«Повтори за мной» — сразу, без мозга (модель отказывается повторять ругательства).
Запуск: ~/Podruga/venv/bin/python devtools/test_repeat.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from intents import repeat_command  # noqa: E402

CASES = {
    "Повтори за мной, Петя дурачок.": ("say", "Петя дурачок"),
    "Повтори: я самая лучшая": ("say", "я самая лучшая"),
    "Петя дурачок, повтори это.": ("say", "Петя дурачок"),
    "скажи за мной привет Петя": ("say", "привет Петя"),
    "repeat after me I love pizza": ("say", "I love pizza"),
    "사랑해 따라 해": ("say", "사랑해"),
    "Отлично, ты можешь начать повторять то, что я тебе говорю?": ("on", ""),
    "повторяй за мной": ("on", ""),
    "хватит повторять": ("off", ""),
    "перестань повторять за мной": ("off", ""),
    "stop repeating": ("off", ""),
    "повтори ещё раз": ("again", ""),
    "повтори что ты сказала": ("again", ""),
    "как дела?": None,
    "я повторил урок вчера": None,
    "скажи какая погода": None,
}
bad = [(t, repeat_command(t), w) for t, w in CASES.items() if repeat_command(t) != w]
for t, got, w in bad:
    print(f"✗ {t!r}: {got!r}, ждали {w!r}")
assert not bad, f"{len(bad)} ошибок"
print("OK")
