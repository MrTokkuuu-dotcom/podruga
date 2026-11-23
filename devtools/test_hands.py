"""«Руки»: нажать, напечатать, клавиши — без настоящих кликов (низкий уровень подменён).
Запуск: ~/Podruga/venv/bin/python devtools/test_hands.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hands  # noqa: E402
from eyes import Element  # noqa: E402
from guard import Blocked, NeedYes  # noqa: E402

bad, log = [], []
hands._ax_press = lambda ref: log.append(("ax", ref)) or ref not in (None, "broken")
hands._mouse_click = lambda x, y: log.append(("click", x, y))
hands._type_unicode = lambda text: log.append(("type", text))
hands._post_key = lambda name: log.append(("key", name))
hands._scroll = lambda dy: log.append(("scroll", dy))
hands._focus = lambda el: log.append(("focus", el.id))
hands.set_overlay_hook(lambda on: log.append(("overlay", on)))
CH = ("Google Chrome", "com.google.Chrome")

play = Element(1, "AXButton", "Play", (100, 100, 40, 20), ref="ok")
hands.press(play, *CH)
if log != [("ax", "ok")]:
    bad.append(f"обычное нажатие: {log}")

log.clear()
broken = Element(2, "AXButton", "Play", (100, 100, 40, 20), ref="broken")
hands.press(broken, *CH)
if log != [("ax", "broken"), ("overlay", True), ("click", 120, 110), ("overlay", False)]:
    bad.append(f"нажатие мышью: {log}")

log.clear()


def boom(x, y):
    log.append(("click", x, y))
    raise RuntimeError("мышь упала")


hands._mouse_click = boom
try:
    hands.press(Element(3, "TEXT", "Войти", (0, 0, 10, 10)), *CH)
except RuntimeError:
    pass
if log[-1] != ("overlay", False):
    bad.append(f"окно не вернули после ошибки: {log}")
hands._mouse_click = lambda x, y: log.append(("click", x, y))

log.clear()
buy = Element(4, "AXButton", "Купить", (0, 0, 10, 10), ref="ok")
try:
    hands.press(buy, *CH)
    bad.append("«Купить» нажалось без вопроса")
except NeedYes:
    pass
if log:
    bad.append(f"при вопросе что-то нажато: {log}")
hands.press(buy, *CH, confirmed=True)
if ("ax", "ok") not in log:
    bad.append("«Купить» после «да» не нажато")

log.clear()
pw = Element(5, "AXTextField", "Пароль", (0, 0, 10, 10), secure=True, ref="ok")
try:
    hands.type_text(pw, "qwerty", *CH)
    bad.append("напечатала в поле пароля")
except Blocked:
    pass
try:
    hands.type_text(Element(6, "AXTextField", "", (0, 0, 10, 10), ref="ok"), "ls", "Terminal", "com.apple.Terminal")
    bad.append("напечатала в Терминал")
except Blocked:
    pass
if any(k == "type" for k, *_ in log):
    bad.append(f"печать прошла: {log}")

log.clear()
field = Element(7, "AXSearchField", "Поиск", (0, 0, 10, 10), ref="ok")
hands.type_text(field, "кино группа крови", *CH, enter=True)
if log != [("focus", 7), ("type", "кино группа крови"), ("key", "enter")]:
    bad.append(f"печать в поиск: {log}")

try:
    hands.key("cmd+q")
    bad.append("cmd+q прошёл")
except ValueError:
    pass
log.clear()
hands.key("enter", *CH)
if log != [("key", "enter")]:
    bad.append(f"enter: {log}")

# в мессенджере Enter = отправить сообщение → только после «да»
log.clear()
try:
    hands.key("enter", "Telegram", "ru.keepcoder.Telegram")
    bad.append("Enter в Telegram без вопроса")
except NeedYes:
    pass
try:
    hands.type_text(field, "привет", "KakaoTalk", "com.kakao.KakaoTalkMac", enter=True)
    bad.append("печать с Enter в KakaoTalk без вопроса")
except NeedYes:
    pass
if log:
    bad.append(f"в мессенджере что-то сделано до «да»: {log}")

log.clear()
hands.scroll("вниз")
hands.scroll("вверх")
if [x[0] for x in log] != ["scroll", "scroll"] or log[0][1] >= 0 or log[1][1] <= 0:
    bad.append(f"листание: {log}")

if bad:
    print("\n".join(bad))
    sys.exit(1)
print("OK")
