"""Живость: взгляд за курсором, движения в простое, одежда по времени суток.
Всё рисует окно — здесь только решаем, что и когда показать."""
import random
import sys
import threading
import time

from journal import now


def _mouse_and_screen():
    """Позиция мыши в координатах «сверху-слева» главного экрана (macOS)."""
    from AppKit import NSEvent, NSScreen
    p = NSEvent.mouseLocation()
    h = NSScreen.screens()[0].frame().size.height
    return p.x, h - p.y


class Life:
    def __init__(self, companion):
        self.c = companion
        self._geom = None
        self._geom_t = 0.0
        self._last = (0.0, 0.0)
        self._next_idle = time.monotonic() + random.uniform(6, 12) * 60
        self._outfit = None

    # --- взгляд ---
    def _gaze_loop(self):
        if sys.platform != "darwin":
            return
        try:
            _mouse_and_screen()
        except Exception as e:
            print(f"[живость] взгляд за курсором выключен: {e}")
            return
        while True:
            time.sleep(0.12)
            c = self.c
            if not c.awake or c.pauser.paused:
                continue
            try:
                t = time.monotonic()
                if self._geom is None or t - self._geom_t > 1.5:     # где окно — не чаще раза в 1.5 с
                    self._geom = c.ui.geometry()
                    self._geom_t = t
                if not self._geom:
                    continue
                x, y, w, h = self._geom
                mx, my = _mouse_and_screen()
                fx, fy = x + w / 2, y + h * 0.2                      # примерно её лицо
                dx = max(-1.0, min(1.0, (mx - fx) / 450))
                dy = max(-1.0, min(1.0, (my - fy) / 320))
                if abs(dx - self._last[0]) + abs(dy - self._last[1]) > 0.06:
                    self._last = (dx, dy)
                    c.ui.look(dx, dy)
            except Exception:
                time.sleep(1)

    # --- движения в простое и одежда ---
    def tick(self):
        c = self.c
        t = now()
        outfit = "night" if (t.hour >= 22 or t.hour < 7) else ""
        if outfit != self._outfit:
            self._outfit = outfit
            c.ui.outfit(outfit)
        if not c.awake or c.pauser.paused or c.speaking:
            return
        if time.monotonic() < self._next_idle or time.monotonic() - c.last_talk < 120:
            return
        late = t.hour >= 23 or t.hour < 3
        c.ui.act("yawn" if late and random.random() < 0.7 else "stretch", 2300)
        self._next_idle = time.monotonic() + random.uniform(7, 15) * 60

    def _tick_loop(self):
        while True:
            try:
                self.tick()
            except Exception as e:
                print(f"[живость] {e}")
            time.sleep(20)

    def start(self):
        threading.Thread(target=self._gaze_loop, name="gaze", daemon=True).start()
        threading.Thread(target=self._tick_loop, name="life", daemon=True).start()
