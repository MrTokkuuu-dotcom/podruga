"""Регрессия учебного прогона: все фразы drill_phrases.txt идут по верному пути (без мозга, ~3 с),
плюс точечные проверки того, что чинили по прогону v34 → v35.
Запуск: ~/Podruga/venv/bin/python devtools/test_drill.py"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import intents  # noqa: E402
import recipes  # noqa: E402

bad = []


def check(name, got, want):
    if got != want:
        bad.append(f"{name}: {got!r} != {want!r}")


# мат и слова-паразиты не мешают командам
check("мат пауза", intents.device_command("бля поставь на паузу"), "МУЗЫКА pause")
check("это самое", intents.device_command("короче это самое включи музыку"), "МУЗЫКА play")
check("как его", intents.device_command("ну это как его сделай громче"), "ГРОМКОСТЬ +10")
check("следующую", intents.device_command("нахуй эту песню, следующую"), "МУЗЫКА next")
check("надоела", intents.device_command("эта песня надоела, переключи"), "МУЗЫКА next")
check("вопрос не команда", intents.device_command("а какая следующая?"), None)
check("останови песню", intents.device_command("останови песню"), "МУЗЫКА pause")
check("пауза опечатка", intents.device_command("поставь на пузу"), "МУЗЫКА pause")
check("включи ≠ выключи", intents.device_command("включи музыкy"), "МУЗЫКА play")
check("засеки", intents.device_command("засеки 3 минуты"), "ТАЙМЕР 3 | таймер")
check("тамер", intents.device_command("поставь тамер на 5 минут"), "ТАЙМЕР 5 | таймер")
check("pause the music", intents.device_command("pause the music"), "МУЗЫКА pause")
# «turn it down» — это тише, а не «сядь»
check("turn it down", intents.device_command("turn it down"), "ГРОМКОСТЬ -10")
check("turn it down не сесть", intents.body_command("turn it down"), None)
check("sit down", intents.body_command("sit down"), "sit")
check("громкость 30", intents.device_command("сделай громкость 30 процентов"), "ГРОМКОСТЬ 30")
check("громкость 50", intents.device_command("поставь громкость на 50"), "ГРОМКОСТЬ 50")
check("напоминания", intents.device_command("какие у меня напоминания"), "НАПОМИНАНИЯ list")
check("рассказ", intents.narrative("я включил телевизор"), True)
check("умеешь", intents.narrative("ты умеешь включать музыку"), True)
check("просьба", intents.narrative("я хочу чтобы ты включила музыку"), False)
check("час", intents.device_command("таймер на 1 час"), "ТАЙМЕР 60 | таймер")
check("два часа", intents.device_command("поставь таймер на два часа"), "ТАЙМЕР 120 | таймер")
check("вежливо", intents.device_command("не могла бы ты поставить на паузу"), "МУЗЫКА pause")
check("в конце фразы", intents.device_command("ничего не слышно, сделай громче"), "ГРОМКОСТЬ +10")
check("умеешь — вопрос", intents.device_command("ты умеешь включать музыку"), None)
check("я спать", intents.is_sleep("всё, я спать"), True)
check("спокойное не сон", intents.is_sleep("включи что-нибудь спокойное"), False)
check("спокойной работы", intents.is_sleep("спокойной работы"), False)
# язык — сразу
check("английский", intents.device_command("давай практиковать английский"), "РЕЖИМ english")
check("корейский", intents.device_command("давай поговорим по-корейски"), "РЕЖИМ корейский")
check("русский", intents.device_command("говори по-русски"), "РЕЖИМ русский")
check("учу — не режим", intents.device_command("я учу английский"), None)
# Mac: новые названия, папки, корейский скриншот
import mac  # noqa: E402
mac.running_apps = lambda: ["Telegram", "Discord", "Steam", "KakaoTalk"]
check("телегу", intents.mac_command("закрой телегу"), ("quit", "Telegram"))
check("дискорд", intents.mac_command("закрой дискорд"), ("quit", "Discord"))
check("стима", intents.mac_command("выйди из стима"), ("quit", "Steam"))
check("браузер", intents.mac_command("закрой браузер"), None)    # Chrome в этом списке не запущен
check("텔레그램", intents.mac_command("텔레그램 닫아줘"), ("quit", "Telegram"))
check("блин закрой", intents.mac_command("блин закрой телеграм"), ("quit", "Telegram"))
check("рабочий стол", intents.mac_command("открой рабочий стол"), ("folder", str(Path.home() / "Desktop")))
check("фотки", intents.mac_command("покажи мои фотки"), ("folder", str(Path.home() / "Pictures")))
check("программы", intents.mac_command("открой папку программы"), ("folder", "/Applications"))
check("스크린샷", intents.mac_command("스크린샷 찍어줘"), ("shot", ""))
# сайты: «ю туб», «епта», «посмотри на ютубе»
check("ю туб", recipes.find("включи кино в ю туб музыке").name, "ytmusic")
check("епта не поиск", recipes.find("епта открой ютуб"), None)
check("короче не в запросе", recipes.find("короче включи кино в ютуб музыке").query, "кино")
check("посмотри на ютубе", recipes.find("посмотри на ютубе новое видео мистера биста").name, "youtube_latest")   # v41: новое — по дате
import actions  # noqa: E402
for w in ("почту", "дискорд", "стим", "телегу", "вотсап", "чат джипити"):
    check(f"знаю «{w}»", actions.known_target(w), True)

# весь набор фраз: маршрут
r = subprocess.run([sys.executable, str(HERE / "drill.py")], capture_output=True, text=True, timeout=300)
fails = [line for line in r.stdout.splitlines() if line.startswith("✗")]
if r.returncode != 0:
    bad.append("drill_phrases.txt:\n  " + "\n  ".join(fails or r.stdout.splitlines()[-5:] + r.stderr.splitlines()[-5:]))

if bad:
    print("FAIL\n" + "\n".join(bad))
    sys.exit(1)
print("OK: прогон фраз и починки v35")
