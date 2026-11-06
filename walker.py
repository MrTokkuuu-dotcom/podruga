"""Прогулки по экрану: иногда, когда вы не разговариваете, она спускается к низу экрана (над Dock),
гуляет туда-сюда, присаживается отдохнуть, а ночью уходит спать в правый угол.
Окно двигаем средствами macOS из главного потока; если его потащили мышкой — она сразу
останавливается. Выключить: значок 🌸 → «Гулять по экрану»."""
import random
import sys
import threading
import time

SPEED = 85            # пикселей в секунду — спокойный шаг
FPS = 30


class Walker:
    def __init__(self, companion):
        self.c = companion
        self.enabled = bool(companion.cfg.get("walk", {}).get("enabled", True))
        self.busy = False            # сейчас идёт или сидит
        self.sitting = False
        self._stop = threading.Event()
        self._next = time.monotonic() + random.uniform(60, 150)
        self._win = None
        self._pos = None             # куда мы сами поставили окно (x, y снизу-слева)
        self._moved_by_user = False

    # ---------- окно (только в главном потоке) ----------
    def _main(self, fn):
        from PyObjCTools import AppHelper
        done = threading.Event()
        box = {}

        def run():
            try:
                box["r"] = fn()
            except Exception as e:
                box["e"] = e
            done.set()
        AppHelper.callAfter(run)
        done.wait(1.0)
        if "e" in box:
            raise box["e"]
        return box.get("r")

    def _window(self):
        if self._win is None:
            from AppKit import NSApp
            for w in NSApp.windows():
                if str(w.title()) == "Подруга":
                    self._win = w
                    break
        return self._win

    def _area(self):
        """(x_min, x_max, y_низ, ширина, высота окна) в координатах macOS (снизу-слева)."""
        def f():
            w = self._window()
            fr = w.frame()
            from AppKit import NSScreen
            vf = (w.screen() or NSScreen.screens()[0]).visibleFrame()
            return (vf.origin.x, vf.origin.x + vf.size.width - fr.size.width, vf.origin.y,
                    fr.origin.x, fr.origin.y)
        return self._main(f)

    def _move(self, x, y):
        def f():
            w = self._window()
            o = w.frame().origin
            if self._pos and (abs(o.x - self._pos[0]) > 4 or abs(o.y - self._pos[1]) > 4):
                self._moved_by_user = True              # её потащили мышкой
                return
            w.setFrameOrigin_((x, y))
            self._pos = (x, y)
        self._main(f)

    # ---------- можно ли сейчас гулять ----------
    def _free(self) -> bool:
        c = self.c
        return (self.enabled and c.awake and not c.pauser.paused and not c.speaking
                and not c.busy.locked() and getattr(c.ui, "mini", True)
                and time.monotonic() - c.last_talk > 40)

    def interrupted(self, by_talk: bool = True) -> bool:
        c = self.c
        if self._stop.is_set() or self._moved_by_user or not getattr(c.ui, "mini", True) or c.pauser.paused:
            return True
        return by_talk and (c.speaking or c.busy.locked())

    # ---------- действия ----------
    def walk_to(self, tx: float | None = None, by_talk: bool = True) -> bool:
        """Дойти до точки tx у нижнего края. Возвращает True, если дошла."""
        try:
            x0, x1, ybot, x, y = self._area()
        except Exception as e:
            print(f"[прогулка] не вижу окно: {e}")
            return False
        if tx is None:
            for _ in range(10):
                tx = random.uniform(x0, x1)
                if abs(tx - x) > 220:
                    break
        tx = max(x0, min(x1, tx))
        self.busy, self._moved_by_user, self._pos = True, False, (x, y)
        self._stop.clear()
        self.c.ui.sit(False)
        dirn = 1 if tx > x else -1
        self.c.ui.walk(dirn)
        ok = False
        try:
            # сначала спускается к низу экрана (плавно), потом идёт
            while not self.interrupted(by_talk):
                dx, dy = tx - x, ybot - y
                if abs(dx) < 2 and abs(dy) < 2:
                    ok = True
                    break
                step = SPEED / FPS
                if abs(dy) > 1:
                    y += max(-step * 2.5, min(step * 2.5, dy))       # вниз быстрее
                else:
                    y = ybot
                    x += max(-step, min(step, dx))
                self._move(x, y)
                time.sleep(1 / FPS)
        finally:
            self.c.ui.walk(0)
            self.busy = False
        return ok

    def sit(self, minutes: float | None = None, sleepy: bool = False):
        self.busy, self.sitting = True, True
        self._stop.clear()
        self.c.ui.sit(True)
        end = time.monotonic() + (minutes or random.uniform(1, 4)) * 60
        try:
            while time.monotonic() < end and not self._stop.is_set():
                if not sleepy and self.interrupted():
                    break
                time.sleep(0.5)
        finally:
            if not sleepy:
                self.c.ui.sit(False)
                self.sitting = False
            self.busy = False

    def stop(self):
        self._stop.set()
        if self.sitting:
            self.c.ui.sit(False)
            self.sitting = False

    def go_corner_and_sleep(self):
        """Перед сном — в правый нижний угол и присесть."""
        if not self.enabled or sys.platform != "darwin":
            return

        def run():
            try:
                _, x1, _, _, _ = self._area()
            except Exception:
                return
            for _ in range(20):                       # дождаться, пока договорит «спокойной ночи»
                if not self.c.speaking:
                    break
                time.sleep(0.25)
            if self.walk_to(x1, by_talk=False):
                self.c.ui.sit(True)
                self.sitting = True
        threading.Thread(target=run, daemon=True).start()

    def wake(self):
        if self.sitting:
            self.c.ui.sit(False)
            self.sitting = False

    # ---------- сама решает ----------
    def _loop(self):
        while True:
            time.sleep(1)
            try:
                if self.busy or time.monotonic() < self._next or not self._free():
                    continue
                r = random.random()
                if r < 0.65:
                    self.walk_to()
                    if random.random() < 0.35 and self._free():
                        self.sit()
                else:
                    self.sit()
                self._next = time.monotonic() + random.uniform(2.5, 7) * 60
            except Exception as e:
                print(f"[прогулка] {e}")
                self.busy = False
                self._next = time.monotonic() + 300

    def command(self, what: str):
        """Из голосовых команд: погуляй / сядь / стой / иди влево / иди вправо."""
        what = (what or "").lower()

        def run():
            if what.startswith("сес") or what.startswith("сид") or what.startswith("сяд"):
                self.sit(3, sleepy=True)
                self.c.ui.sit(False); self.sitting = False
            elif what.startswith("стоп"):
                self.stop()
            else:
                try:
                    x0, x1, _, x, _ = self._area()
                except Exception:
                    return
                tx = x0 if "лев" in what else x1 if "прав" in what else None
                time.sleep(0.6)
                self.walk_to(tx, by_talk=False)
        self.stop()
        time.sleep(0.1)
        threading.Thread(target=run, daemon=True).start()

    def start(self):
        if sys.platform == "darwin":
            threading.Thread(target=self._loop, name="walker", daemon=True).start()
