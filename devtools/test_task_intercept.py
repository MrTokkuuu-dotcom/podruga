"""Задачи «глаз и рук» внутри Подруги: «стоп» и «да/нет» посреди задачи, разрешения, выключатель.
Без экрана: глаза, рецепты и агент подменены. Запуск: ~/Podruga/venv/bin/python devtools/test_task_intercept.py"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agent  # noqa: E402
import eyes  # noqa: E402
import recipes  # noqa: E402
import tasks  # noqa: E402

bad = []


class UI:
    def __init__(self):
        self.lines, self.boxes = [], []

    def add(self, role, text, tag=None):
        self.lines.append((role, text, tag))

    def highlight(self, frame):
        self.boxes.append(frame)


class Journal:
    def log(self, *a, **k):
        pass


class Comp:
    def __init__(self, enabled=True):
        self.cfg = {"hands": {"enabled": enabled, "google_fallback": True}}
        self.said, self.ui, self.journal = [], UI(), Journal()
        self.local = self.google = None

    def say(self, text, emotion="calm"):
        self.said.append(text)


asked_perm = []
eyes.permissions = lambda: {"accessibility": True, "screen": True}
eyes.ask_permissions = lambda which="accessibility": asked_perm.append(which)

# 1) задачи нет — «стоп» не наш
tr = tasks.TaskRunner(Comp())
if tr.intercept("стоп"):
    bad.append("без задачи «стоп» съеден")

# 2) задача идёт: «стоп» останавливает
started = threading.Event()


class SlowTask:
    def __init__(self, goal, think, eyes_mod, hands_mod, ask_yes, say, look_google=None, stop=None, **k):
        self.stop, self.ask_yes = stop, ask_yes

    def run(self):
        started.set()
        while not self.stop.is_set():
            time.sleep(0.01)
        return agent.Result(False, "остановилась", 1)


agent.Task = SlowTask
recipes.find = lambda goal: None
c = Comp()
tr = tasks.TaskRunner(c)
tr.start("открой настройки ютуба")
started.wait(2)
if not tr.running:
    bad.append("задача не отмечена как идущая")
if not tr.intercept("Аня, стоп!"):
    bad.append("«стоп» во время задачи не съеден")
tr.join(2)
if tr.running:
    bad.append("после «стоп» задача не закончилась")

# 3) вопрос «да/нет»: «как дела» не ответ, «да» — ответ
answers = []


class AskTask(SlowTask):
    def run(self):
        answers.append(self.ask_yes("Нажать «Купить»?"))
        answers.append(self.ask_yes("Нажать «Удалить»?"))
        return agent.Result(True, "готово", 2)


agent.Task = AskTask
c = Comp()
tr = tasks.TaskRunner(c, confirm_timeout=2)
tr.start("купи")
for _ in range(200):
    if tr.waiting:
        break
    time.sleep(0.01)
if tr.intercept("как дела"):
    bad.append("«как дела» съеден как ответ")
if not tr.intercept("да"):
    bad.append("«да» не съеден")
for _ in range(200):
    if tr.waiting and len(answers) == 1:
        break
    time.sleep(0.01)
tr.intercept("нет, не надо")
tr.join(3)
if answers != [True, False]:
    bad.append(f"ответы {answers}, ждал [True, False]")
if "Нажать «Купить»?" not in c.said:
    bad.append("вопрос не сказан вслух")

# 4) молчание = «нет»
answers.clear()
c = Comp()
tr = tasks.TaskRunner(c, confirm_timeout=0.2)
tr.start("купи")
tr.join(3)
if answers != [False, False]:
    bad.append(f"молчание: {answers}")

# 5) нет «Универсального доступа» — внятная фраза, агент не запущен
ran = []
agent.Task = lambda *a, **k: ran.append(1)
eyes.permissions = lambda: {"accessibility": False, "screen": True}
c = Comp()
tasks.TaskRunner(c).run("включи песню")
if not any("Универсальный доступ" in s for s in c.said) or asked_perm != ["accessibility"] or ran:
    bad.append(f"без разрешения: {c.said} {asked_perm} {ran}")
eyes.permissions = lambda: {"accessibility": True, "screen": True}

# 6) руки выключены в настройках
c = Comp(enabled=False)
tasks.TaskRunner(c).run("включи песню")
if not c.said or ran:
    bad.append("выключенные руки всё равно что-то делают")

# 7) рецепт справился — агент не нужен
recipes.find = lambda goal: recipes.Recipe("ytmusic", "https://music.youtube.com/search?q=x", None)
recipes.run = lambda r, e, h, o, **k: True
c = Comp()
tasks.TaskRunner(c).run("включи x в ютуб музыке")
if ran or not c.said:
    bad.append(f"рецепт: агент={ran} сказала={c.said}")

# 8) вторая задача, пока идёт первая (v41): новая просьба главнее — прежнюю молча бросаем, начинаем новую
agent.Task = SlowTask
recipes.find = lambda goal: None
started.clear()
c = Comp()
tr = tasks.TaskRunner(c)
tr.start("раз")
started.wait(2)
started.clear()
tr.start("два")
if any("подожди" in s.lower() for s in c.said) or any("остановилась" in s.lower() for s in c.said):
    bad.append(f"новая просьба посреди дела: {c.said}")
if not started.wait(2) or not tr.running:
    bad.append("вторая задача не началась")
tr.intercept("стоп")
tr.join(2)

# 9) Google-координаты 0–1000 переводятся в точки экрана
got = tasks.to_points("<<НАЖАТЬ 500, 250>>", (1512, 982))
if got != "<<НАЖАТЬ 756, 246>>":
    bad.append(f"перевод координат: {got}")

if bad:
    print("\n".join(bad))
    sys.exit(1)
print("OK")
