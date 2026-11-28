"""Самообучение: выученные задачи (learned.py) и поправки (lessons.py). Без настоящего экрана.
Запуск: ~/Podruga/venv/bin/python devtools/test_learn.py"""
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agent  # noqa: E402
import guard  # noqa: E402
import learned  # noqa: E402
import lessons  # noqa: E402
from eyes import Element  # noqa: E402

bad = []


def check(name, got, want):
    if got != want:
        bad.append(f"{name}: {got!r} != {want!r}")


tmp = Path(tempfile.mkdtemp())

# --- запись и поиск ---
trace = [{"do": "press", "label": "Поиск", "role": "AXButton"},
         {"do": "type", "label": "Поиск", "role": "AXTextField", "text": "Кино"},
         {"do": "key", "name": "enter"},
         {"do": "press", "label": "Воспроизвести Кино", "role": "AXButton"}]
book = learned.Learned(tmp / "learned.json")
key = book.record("включи кино в яндекс музыке", trace)
check("шаблон", key, "включи {q} в яндекс музыке")
check("шаг подставной", book.items[key]["steps"][1]["text"], "{q}")
check("кнопка подставная", book.items[key]["steps"][3]["label"], "воспроизвести {q}")
check("найти другое", book.find("Включи Сплин в Яндекс музыке"), (key, "сплин"))
check("не то", book.find("открой почту"), None)
check("общее не шаблон", learned.make_entry("включи кино", trace)[0], "включи кино")
check("координаты не учим", learned.make_entry("нажми там", [{"do": "press", "label": "точка 10,20"}]), None)
book2 = learned.Learned(tmp / "learned.json")              # с диска
check("с диска", book2.find("включи сплин в яндекс музыке"), (key, "сплин"))


# --- повтор по записи ---
@dataclass
class Snap:
    app: str = "Safari"
    bundle_id: str = "com.apple.Safari"
    elements: list = field(default_factory=list)

    def get(self, i):
        return next((e for e in self.elements if e.id == i), None)


class Eyes:
    def __init__(self, screens):
        self.screens, self.i = screens, 0

    def snapshot(self):
        s = self.screens[min(self.i, len(self.screens) - 1)]
        return Snap(elements=s)

    def read_text(self):
        return []


class Hands:
    def __init__(self, eyes):
        self.log, self.eyes = [], eyes

    def press(self, el, app, bid, confirmed=False, mouse=False):
        guard.check_press(el.label, confirmed)
        self.log.append(("press", el.label))
        self.eyes.i += 1
        return "ok"

    def type_text(self, el, text, app, bid, enter=False, confirmed=False):
        self.log.append(("type", text))
        return "ok"

    def key(self, name, app="", bundle_id="", confirmed=False):
        self.log.append(("key", name))
        return "ok"

    def scroll(self, d):
        self.log.append(("scroll", d))


E = lambda i, label, role="AXButton": Element(i, role, label, (0, 0, 10, 10), ref=object())  # noqa: E731
screens = [[E(1, "Поиск"), E(2, "Поиск", "AXTextField")],
           [E(1, "Поиск"), E(2, "Поиск", "AXTextField"), E(3, "Воспроизвести Сплин")],
           [E(1, "Ещё")]]
eyes = Eyes(screens)
hands = Hands(eyes)
stop = threading.Event()
t = [0.0]
ok = learned.replay(book.items[key], "сплин", eyes, hands, lambda q: True, None, stop,
                    clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
check("повтор", ok, True)
check("повтор шаги", hands.log, [("press", "Поиск"), ("type", "сплин"), ("key", "enter"),
                                 ("press", "Воспроизвести Сплин")])
eyes = Eyes([[E(1, "Что-то другое")]])
ok = learned.replay(book.items[key], "сплин", eyes, Hands(eyes), lambda q: True, None, stop,
                    clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
check("не нашла — False", ok, False)
book.done(key, False)
check("одна неудача — помнит", key in book.items, True)
book.done(key, False)
check("две — забыла", key in book.items, False)
# опасная кнопка при повторе — спрашивает «да»
eyes = Eyes([[E(1, "Купить")]])
asked = []
ok = learned.replay({"steps": [{"do": "press", "label": "Купить", "role": "AXButton"}]}, None, eyes, Hands(eyes),
                    lambda q: asked.append(q) or False, None, stop,
                    clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
check("купить без да", (ok, bool(asked)), (False, True))

# --- агент пишет, что делал ---
answers = iter(["<<НАЖАТЬ 1>>", "<<ПЕЧАТАТЬ 2 | Кино>>", "<<КЛАВИША enter>>", "<<ГОТОВО включила>>"])


class AEyes(Eyes):
    def format_for_brain(self, snap):
        return "..."


ae = AEyes([[E(1, "Поиск"), E(2, "Поле", "AXTextField"), E(3, "a"), E(4, "b"), E(5, "c")]])
ah = Hands(ae)
ah.press = lambda el, app, bid, confirmed=False, mouse=False: "нажала"
task = agent.Task("включи кино на ютубе", lambda p: next(answers), ae, ah, lambda q: True, lambda *a: None,
                  sleep=lambda s: None)
res = task.run()
check("агент ок", res.ok, True)
check("агент след", [s["do"] for s in task.trace], ["press", "type", "key"])

# --- поправки ---
C = lessons.command
check("имел в виду", C("Нет, я имел в виду ютуб музыку", "включи музыку", "Включаю!", True),
      ("meant", "включи ютуб музыку"))
check("имел в виду полное", C("нет я имел в виду открой телеграм", "открой почту", "", True),
      ("meant", "открой телеграм"))
check("не после дела", C("я имел в виду другое кино", "какое кино посмотреть", "Интерстеллар", False), None)
check("не называй", C("Не называй меня зайкой", None, None, False), ("rule", "Не называй его «зайкой»."))
check("не говори так", C("не говори так больше", "как дела", "Ну ты и соня!", False),
      ("rule", "Не говори так, как сказала тут: «Ну ты и соня!»."))
check("короче", C("говори покороче", None, None, False), ("rule", "Отвечай покороче."))
check("правило", C("запомни правило: всегда называй цены в вонах", None, None, False),
      ("rule", "Всегда называй цены в вонах."))
check("обычная фраза", C("больше не хочу есть", None, None, False), None)
check("обычная 2", C("мне не нравится эта песня", None, None, True), None)
check("список", C("чему ты научилась?", None, None, False), ("list",))
check("забудь", C("забудь это правило", None, None, False), ("forget",))
check("забудь всё", C("забудь всё, чему научилась", None, None, False), ("forget_all",))

L = lessons.Lessons(tmp / "lessons.json")
L.add_alias("включи музыку", "включи ютуб музыку")
check("замена", L.rewrite("Включи музыку!"), "включи ютуб музыку")
check("замена опечатка", L.rewrite("включи музыкy"), "включи ютуб музыку")
check("без замены", L.rewrite("выключи музыку"), "выключи музыку")
L.add_rule("Не называй его «зайкой».")
check("дубль", L.add_rule("Не называй его «зайкой»."), False)
check("в подсказке", "зайкой" in L.prompt_block("Дима"), True)
L2 = lessons.Lessons(tmp / "lessons.json")
check("с диска", (L2.rewrite("включи музыку"), len(L2.rules)), ("включи ютуб музыку", 1))
check("забыть последнее", L2.forget_last(), "Не называй его «зайкой».")
check("забыть всё", L2.forget_all(), 1)

print("\n".join(bad) if bad else "OK")
sys.exit(1 if bad else 0)
