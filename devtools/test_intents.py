"""Мгновенные команды музыке, громкости, таймеру. Запуск: ~/Podruga/venv/bin/python devtools/test_intents.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from intents import body_command, device_command  # noqa: E402

CASES = {
    "включи музыку": "МУЗЫКА play",
    "Аня, включи музыку пожалуйста": "МУЗЫКА play",
    "следующая песня": "МУЗЫКА next",
    "переключи трек": "МУЗЫКА next",
    "верни прошлую песню": "МУЗЫКА prev",
    "поставь на паузу": "МУЗЫКА pause",
    "выключи музыку": "МУЗЫКА pause",
    "сделай громче": "ГРОМКОСТЬ +10",
    "погромче": "ГРОМКОСТЬ +10",
    "тише": "ГРОМКОСТЬ -10",
    "сделай потише": "ГРОМКОСТЬ -10",
    "выключи звук": "ГРОМКОСТЬ mute",
    "таймер на 5 минут": "ТАЙМЕР 5 | таймер",
    "поставь таймер на 15 минут": "ТАЙМЕР 15 | таймер",
    "play music": "МУЗЫКА play",
    "next song": "МУЗЫКА next",
    "turn it up": "ГРОМКОСТЬ +10",
    "음악 틀어줘": "МУЗЫКА play",
    "다음 곡": "МУЗЫКА next",
    "소리 줄여줘": "ГРОМКОСТЬ -10",
    "не включай музыку": None,
    "включи звук": None,
    "поставь музыку потише": "ГРОМКОСТЬ -10",
    "сделай музыку погромче": "ГРОМКОСТЬ +10",
    "skip this part": None,
    "а какая следующая": None,
    "я вчера слушал классную музыку на концерте": None,
    "тише едешь дальше будешь": None,
    "как дела?": None,
    "какую музыку ты любишь?": None,
    "таймер": None,
}
bad = [(t, device_command(t), want) for t, want in CASES.items() if device_command(t) != want]
for t, got, want in bad:
    print(f"✗ {t!r}: {got!r}, ждали {want!r}")
assert not bad, f"{len(bad)} ошибок"
# «глаза и руки»: просьбы, которые она делает сама на экране
from intents import task_command  # noqa: E402
for t, want in [("включи цоя в ютуб музыке", "СДЕЛАТЬ включи цоя в ютуб музыке"),
                ("найди на ютубе как варить рамен", "СДЕЛАТЬ найди на ютубе как варить рамен"),
                ("включи музыку", None), ("как дела?", None), ("я вчера смотрел ютуб", None)]:
    assert task_command(t) == want, (t, task_command(t))
assert device_command("включи музыку") == "МУЗЫКА play"
# готовый ответ «открой {что}» — только для известных сайтов и программ, остальное — мозгу (он может СДЕЛАТЬ)
import actions  # noqa: E402
for what, want in [("ютуб", True), ("https://naver.com", True), ("телеграм", True), ("сафари", True),
                   ("его какие-нибудь видосики первый второй первый", False),
                   ("на этот мьюзик песню егора крида будильник", False)]:
    assert actions.known_target(what) == want, (what, actions.known_target(what))
# старое поведение телу не изменилось
assert body_command("присядь") == "sit" and body_command("включи музыку") is None
print("OK")
