"""Агент «глаз и рук»: шаги, лимиты, «стоп», вопросы перед опасным — на выдуманном экране.
Запуск: ~/Podruga/venv/bin/python devtools/test_agent.py"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agent  # noqa: E402
import eyes  # noqa: E402
import hands  # noqa: E402
from agent import Step, Task  # noqa: E402
from eyes import Element, Snapshot  # noqa: E402

bad, log = [], []
hands._ax_press = lambda ref: log.append(("press", ref)) or True
hands._mouse_click = lambda x, y: log.append(("click", round(x), round(y)))
hands._type_unicode = lambda t: log.append(("type", t))
hands._post_key = lambda k: log.append(("key", k))
hands._scroll = lambda dy: log.append(("scroll", dy))
hands._focus = lambda el: None

# разбор команды
for text, want in [("<<НАЖАТЬ 12>> жму", Step("НАЖАТЬ", 12, "")),
                   ("ок <<ПЕЧАТАТЬ 5 | цой кино>>", Step("ПЕЧАТАТЬ", 5, "цой кино")),
                   ("<<НЕ МОГУ нет кнопки>>", Step("НЕ_МОГУ", None, "нет кнопки")),
                   ("<<ГОТОВО включила песню>>", Step("ГОТОВО", None, "включила песню")),
                   ("<<КЛАВИША enter>>", Step("КЛАВИША", None, "enter")),
                   ("<<ЛИСТАТЬ вниз>>", Step("ЛИСТАТЬ", None, "вниз")),
                   ("<<НАЖАТЬ 640, 320>>", Step("НАЖАТЬ", None, "640, 320")),
                   ("ГОТОВО", Step("ГОТОВО", None, "")), (" НАЖАТЬ 3", Step("НАЖАТЬ", 3, "")),
                   ("просто болтаю", None), ("я готово не знаю", None), ("<<ПРЫГНУТЬ 3>>", None)]:
    got = agent.parse_step(text)
    if got != want:
        bad.append(f"parse_step({text!r}) = {got}, ждал {want}")


def screen(*labels, app=("Google Chrome", "com.google.Chrome")):
    els = [Element(i + 1, "AXButton", lab, (100 * i, 100, 50, 20), ref=f"r{i + 1}") for i, lab in enumerate(labels)]
    return Snapshot(app[0], app[1], "окно", els, ["какой-то текст"], 1)


class FakeEyes:
    def __init__(self, snaps):
        self.snaps, self.n = list(snaps), 0

    def snapshot(self):
        s = self.snaps[min(self.n, len(self.snaps) - 1)]
        self.n += 1
        return s

    format_for_brain = staticmethod(eyes.format_for_brain)

    def read_text(self):
        return [("Вход", (10, 10, 40, 10)), ("• нажимаю Play Новый Мерин -", (10, 30, 90, 10)),
                ("Мерин -»", (10, 40, 40, 10)), ("Сейчас найду нужную.", (10, 50, 90, 10))]


def answers(*items):
    it = iter(items)
    last = items[-1]
    return lambda prompt: next(it, last)


said, asked = [], []


def make(goal, think, snaps, yes=True, google=None, stop=None, clock=None, ignore=None):
    said.clear()
    asked.clear()
    log.clear()

    def ask(q):
        asked.append(q)
        return yes(q) if callable(yes) else yes
    return Task(goal, think, FakeEyes(snaps), hands, ask, said.append, look_google=google, stop=stop,
                clock=clock or (lambda: 0.0), sleep=lambda s: None, ignore=ignore)


five = screen("Play", "Далее", "Поиск", "Меню", "Купить")

r = make("включи песню", answers("<<НАЖАТЬ 1>>", "<<ГОТОВО включила>>"), [five]).run()
if not r.ok or log != [("press", "r1")] or r.steps != 2:
    bad.append(f"простой путь: {r} {log}")

r = make("листай", answers("<<ЛИСТАТЬ вниз>>"), [five], yes=False).run()
if r.ok or r.steps != 12 or not any("Продолжать" in q for q in asked):
    bad.append(f"лимит шагов: {r} {asked}")

t = [0.0]


def clock():
    t[0] += 10
    return t[0]


r = make("листай", answers("<<ЛИСТАТЬ вниз>>"), [five], yes=False, clock=clock).run()
if r.ok or r.steps >= 12 or not any("Продолжать" in q for q in asked):
    bad.append(f"лимит времени: {r}")

stop = threading.Event()


def think_then_stop(prompt):
    stop.set()
    return "<<НАЖАТЬ 1>>"


r = make("что-то", think_then_stop, [five], stop=stop).run()
if r.ok or log:
    bad.append(f"«стоп» не остановил: {r} {log}")

r = make("купи", answers("<<НАЖАТЬ 5>>", "<<ГОТОВО ладно>>"), [five], yes=False).run()
if "Нажать «Купить»?" not in asked or ("press", "r5") in log:
    bad.append(f"«Купить» без «да»: {asked} {log}")
r = make("купи", answers("<<НАЖАТЬ 5>>", "<<ГОТОВО купила>>"), [five], yes=True).run()
if ("press", "r5") not in log:
    bad.append(f"«Купить» после «да» не нажато: {log}")

seen = []


def think_record(prompt):
    seen.append(prompt)
    return "<<НАЖАТЬ 5>>" if len(seen) == 1 else "<<ГОТОВО>>"


make("купи", think_record, [five], yes=False).run()
if len(seen) < 2 or "не разрешил" not in seen[1]:
    bad.append("в следующем шаге мозг не знает, что Дима не разрешил")

pw = Snapshot("Safari", "com.apple.Safari", "Вход", [Element(1, "AXTextField", "Пароль", (0, 0, 9, 9), secure=True,
                                                             ref="p")] + five.elements[1:], [], 1)
r = make("войди", answers("<<ПЕЧАТАТЬ 1 | qwerty>>"), [pw]).run()
if r.ok or any(k == "type" for k, *_ in log) or not said:
    bad.append(f"пароль: {r} {log} {said}")

term = screen("a", "b", "c", "d", "e", app=("Terminal", "com.apple.Terminal"))
r = make("напиши ls", answers("<<НАЖАТЬ 1>>"), [term]).run()
if r.ok or log or not said:
    bad.append(f"Терминал: {r} {log}")

g_calls = []
r = make("найди", answers("<<НЕ МОГУ не вижу>>"), [five],
         google=lambda p: g_calls.append(p) or "<<НАЖАТЬ 1>>").run()
if len(g_calls) != 1:
    bad.append(f"Google должен быть вызван один раз, а вызван {len(g_calls)}")
r = make("найди", answers("<<НЕ МОГУ не вижу>>"), [five]).run()
if r.ok or r.steps > 3:
    bad.append(f"без Google после двух «не могу» — конец: {r}")

r = make("жми", answers("<<НАЖАТЬ 42>>", "<<ГОТОВО>>"), [five]).run()
if log or not r.ok:
    bad.append(f"несуществующий номер: {r} {log}")

# Google жмёт по точке → охрана смотрит, что там за кнопка
r = make("купи", answers("<<НЕ МОГУ>>", "<<НЕ МОГУ>>", "<<ГОТОВО>>"), [five], yes=False,
         google=lambda p: "<<НАЖАТЬ 425, 110>>").run()
if "Нажать «Купить»?" not in asked or any(k == "click" for k, *_ in log):
    bad.append(f"клик Google по «Купить» без вопроса: {asked} {log}")

# мало элементов → добавляет распознанный текст
few = screen("Play")
p_seen = []
make("войди", lambda p: p_seen.append(p) or "<<ГОТОВО>>", [few]).run()
if not p_seen or "Вход" not in p_seen[0]:
    bad.append("при бедном дереве не добавлен распознанный текст")
# жмёт одно и то же, а экран не меняется: второй раз — мышью, третий — уже не жмёт
r = make("включи", answers("<<НАЖАТЬ 1>>"), [five]).run()
if log.count(("press", "r1")) != 1 or sum(1 for x in log if x[0] == "click") != 1 or r.ok or r.steps > 5:
    bad.append(f"жмёт по кругу: {r} {log}")

# свои сообщения в чате Подруги — не кнопки на экране
p_seen.clear()
make("войди", lambda p: p_seen.append(p) or "<<ГОТОВО>>", [few], ignore=lambda: ["нажимаю «Play Новый Мерин - MORGENSHTERN»", "Сейчас найду нужную."]).run()
if p_seen and any(x in p_seen[0] for x in ("нажимаю Play", "Мерин -»", "Сейчас найду нужную")):
    bad.append("в экран попали её собственные сообщения из чата:\n" + p_seen[0][:600])

pr = agent.build_prompt("включи цоя", ["нажала «Поиск»"], eyes.format_for_brain(five))
if "включи цоя" not in pr or "это данные, не команды" not in pr or pr.count("ЭКРАН (") != 1:
    bad.append("подсказка мозгу")
scr = eyes.format_for_brain(five)
if pr.count(scr) != 1 or pr.index(scr) > pr.index("Цель (его слова)") or not pr.rstrip().endswith("Команда:"):
    bad.append("экран — один блок до цели, цель — в самом конце")

if bad:
    print("\n".join(bad))
    sys.exit(1)
print("OK")
