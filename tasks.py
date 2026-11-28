"""Задачи «глаз и рук» внутри Подруги: одна за раз, в своём потоке.
Сначала рецепт (recipes.py), не вышло — агент (agent.py). Пока задача идёт, «стоп» понимается всегда,
а на вопрос «Нажать «Купить»?» она ждёт «да» до 20 с (молчание — «нет»). Остальные фразы — обычный разговор."""
import re
import sys
import threading

import agent
import eyes
import learned
import guard
import hands
import recipes

NO_ACCESS = ("Чтобы нажимать за тебя, включи мне «Универсальный доступ»: Системные настройки → "
             "Конфиденциальность и безопасность → Универсальный доступ → «Подруга». Я открыла это окно.")
DONE_LINES = {"ytmusic": "Включила!", "youtube": "Вот, открыла.", "coupang": "Вот, нашла на Купанге.",
              "naver": "Вот, в Навере.", "google": "Вот, нашла."}


def to_points(answer: str, screen: tuple) -> str:
    """Google отвечает координатами 0–1000 по снимку → точки экрана."""
    def conv(m):
        x = int(int(m.group(1)) * screen[0] / 1000 + 0.5)
        y = int(int(m.group(2)) * screen[1] / 1000 + 0.5)
        return f"<<НАЖАТЬ {x}, {y}>>"
    return re.sub(r"<<\s*НАЖАТЬ\s+(\d+)\s*,\s*(\d+)\s*>>", conv, answer)


class TaskRunner:
    def __init__(self, comp, confirm_timeout: float = guard.CONFIRM_TIMEOUT):
        self.c = comp
        self.confirm_timeout = confirm_timeout
        self.stop = threading.Event()
        self.running = False
        self.waiting = False
        self._answer = None
        self._got = threading.Event()
        self._thread = None

    # --- что он сказал во время задачи ---
    def intercept(self, text: str) -> bool:
        if not self.running:
            return False
        if guard.is_stop(text):
            self.stop.set()
            self._answer = False
            self._got.set()
            return True
        if self.waiting:
            yn = guard.yes_no(text)
            if yn is None:
                return False
            new = len(text.split()) > 4              # «нет, ты зашла не туда, нужен ITpedia» — это новая просьба
            self._answer = yn and not new
            if new:
                self.stop.set()                      # прежнее бросаем, новое поймёт мозг и начнёт заново
            self._got.set()
            return not new
        return False

    def ask_yes(self, question: str) -> bool:
        if self.stop.is_set():
            return False
        self._got.clear()
        self._answer = None
        self.waiting = True
        try:
            self.c.ui.add("her", question, "❓")
            self.c.say(question, "think")
            ok = self._got.wait(self.confirm_timeout) and bool(self._answer)
        finally:
            self.waiting = False
        if not ok and not self.stop.is_set():
            self.c.ui.add("sys", "Не стала: нет ответа «да»")
        return ok

    def book(self):
        """Выученные задачи (data/learned.json); None — самообучение выключено в настройках."""
        if not self.c.cfg.get("hands", {}).get("learn", True) or "_data_dir" not in self.c.cfg:
            return None
        if getattr(self, "_book", None) is None:
            self._book = learned.Learned(self.c.cfg["_data_dir"] / "learned.json")
        return self._book

    # --- запуск ---
    def start(self, goal: str, fn=None, said: str | None = None) -> None:
        """fn — своё дело вместо рецепта/агента (например, «закрой телеграм» со своим вопросом «да?»)."""
        if self.running:                                 # новая просьба посреди дела — главнее старой
            print(f"[руки] новая просьба — бросаю прежнее: {goal}")
            self._quiet_stop = True                      # старое молча, без «Остановилась»
            self.stop.set()
            self._answer = False
            self._got.set()
            if self._thread:
                self._thread.join(8)
            if self.running:
                self.c.say("Подожди, я ещё с прошлым вожусь. Скажи «стоп», если не нужно.")
                return
        self.running = True
        self._quiet_stop = False
        self._said = said if said and said.strip() != goal.strip() else None   # его слова — чтобы узнать в следующий раз
        self.stop.clear()
        self._thread = threading.Thread(target=self._run_safe, args=(goal, fn), name="task", daemon=True)
        self._thread.start()

    def join(self, timeout=None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def _run_safe(self, goal: str, fn=None) -> None:
        try:
            fn() if fn is not None else self.run(goal)
        except Exception as e:
            print(f"[руки] ошибка: {e}")
            self.c.say("Ой, не получилось. Что-то пошло не так.", "sad")
        finally:
            self.running = False
            self._ui_box(None)

    def _ui_box(self, frame) -> None:
        f = getattr(self.c.ui, "highlight", None)
        if f:
            f(frame)

    def _on_step(self, text: str, el=None) -> None:
        print(f"[руки] {text}")
        self.c.ui.add("her", text, "👆" if el is not None else "👀")
        self._ui_box(el.frame if el is not None else None)

    def _think(self, prompt: str) -> str:
        loc, g = self.c.local, self.c.google
        b = loc if loc is not None and not getattr(loc, "failed", False) and loc.ready.is_set() else g
        if b is None:
            raise RuntimeError("нечем думать")
        opts = {"temperature": 0.2, "max_tokens": 60}
        if b is loc and prompt.startswith(agent.RULES):
            opts["static"] = agent.RULES                  # правила агента — из кэша
        return b.chat([{"role": "user", "content": prompt}], opts)

    def _look_google(self, prompt: str) -> str:
        import vision
        from AppKit import NSScreen
        img = vision.capture()
        if not img:
            return "<<НЕ МОГУ не вижу экран>>"
        sz = NSScreen.mainScreen().frame().size
        extra = ("\nК сообщению приложен снимок этого экрана. Если нужного нет в списке, ответь <<НАЖАТЬ x, y>>, "
                 "где x и y — от 0 до 1000 по ширине и высоте снимка.")
        text = "".join(self.c.google.stream_reply("", [], text=prompt + extra, image=img))
        return to_points(text, (sz.width, sz.height))

    def run(self, goal: str) -> None:
        c = self.c
        h = c.cfg.get("hands", {})
        if not h.get("enabled", True):
            c.say("Руки у меня сейчас выключены в настройках — включи «Глаза и руки», и сделаю.")
            return
        if sys.platform != "darwin":
            c.say("Нажимать за тебя я пока умею только на Mac.")
            return
        if not eyes.permissions().get("accessibility"):
            c.say(NO_ACCESS)
            eyes.ask_permissions("accessibility")
            return
        print(f"[руки] задача: {goal}")
        import actions
        r = recipes.find(goal)
        if r is not None:
            self._on_step(f"ищу: {r.url}")
            try:
                ok = recipes.run(r, eyes, hands, actions.open_thing)
            except guard.Blocked as b:
                c.say(b.reason)
                return
            if ok:
                c.journal.log("action", what=f"рецепт {r.name}: {goal}")
                if r.name in ("ytmusic", "youtube"):
                    import mac
                    mac.note_media()                 # теперь «пауза» / «дальше» знают, чем управлять
                c.say(DONE_LINES.get(r.name, "Готово!"), "joy")
                return
            print("[руки] рецепт не справился — дальше сама")
        book = self.book()
        hit = book.find(goal) if book is not None else None
        if hit is not None:
            key, q = hit
            self._on_step("делаю, как в прошлый раз")
            try:
                ok = learned.replay(book.items[key], q, eyes, hands, self.ask_yes, actions.open_thing, self.stop,
                                    on_step=self._on_step)
            except guard.Blocked as b:
                c.say(b.reason)
                return
            book.done(key, ok)
            if self.stop.is_set():
                c.say("Остановилась.")
                return
            if ok:
                print(f"[учусь] сделала по выученному: «{key}»" + (f" ({q})" if q else ""))
                c.journal.log("action", what=f"по выученному: {goal}")
                c.say("Готово!", "joy")
                return
            print("[учусь] по выученному не вышло — дальше сама")
        look = self._look_google if (h.get("google_fallback", True) and c.google is not None) else None
        spoken = []

        def say(text, emotion="calm"):
            spoken.append(text)
            c.say(text, emotion)
        task = agent.Task(goal, self._think, eyes, hands, self.ask_yes, say, look_google=look, stop=self.stop,
                          open_fn=actions.open_thing, on_step=self._on_step,
                          ignore=lambda: spoken + [h.get("text", "") for h in list(getattr(c, "history", []))[-12:]])
        res = task.run()
        print(f"[руки] итог: {res}")
        if res.ok and not task.denied and not self.stop.is_set() and book is not None:
            key = book.record(goal, task.trace)
            said = getattr(self, "_said", None)
            if said:
                key = book.record(said, task.trace) or key
            if key:
                print(f"[учусь] запомнила, как делать «{key}»: {len(task.trace)} шагов")
                c.ui.add("sys", "Запомнила, как это делается — в следующий раз будет быстрее.")
        c.journal.log("action", what=f"задача «{goal}»: {'да' if res.ok else 'нет'} за {res.steps} шагов")
        if self.stop.is_set():
            if not getattr(self, "_quiet_stop", False):
                c.say("Остановилась.")
        elif res.ok:
            msg = res.message.strip(" .")
            plain = len(msg) < 4 or msg.lower() in ("готово", "что сделала", "коротко", "коротко, что сделала")
            c.say("Готово!" if plain else msg[0].upper() + msg[1:] + ".", "joy")
        elif res.message not in spoken:              # охрана уже сама объяснила — не повторяем
            c.say(res.message, "sad")
