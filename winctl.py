"""Окно «Подруги» средствами macOS (всё — в главном потоке): рамка, размер, экран,
и «клики насквозь» — пустая прозрачная часть окна пропускает мышку к тому, что под ним."""
import sys
import threading
import time

_win = None


def main(fn, timeout: float = 1.0):
    """Выполнить fn в главном потоке и вернуть результат."""
    from PyObjCTools import AppHelper
    done, box = threading.Event(), {}

    def run():
        try:
            box["r"] = fn()
        except Exception as e:
            box["e"] = e
        done.set()
    AppHelper.callAfter(run)
    done.wait(timeout)
    if "e" in box:
        raise box["e"]
    return box.get("r")


def window():
    global _win
    if _win is None:
        from AppKit import NSApp
        for w in NSApp.windows():
            if str(w.title()) == "Подруга":
                _win = w
                break
    return _win


def frame():
    """(x, y, w, h) окна в координатах macOS (снизу-слева)."""
    def f():
        fr = window().frame()
        return fr.origin.x, fr.origin.y, fr.size.width, fr.size.height
    return main(f)


def set_frame(x, y, w, h):
    main(lambda: window().setFrame_display_(((x, y), (w, h)), True))


def screen_frames():
    """Рамка экрана и его видимая часть (без Dock и меню): ((x, y, w, h), (x, y, w, h))."""
    def f():
        from AppKit import NSScreen
        win = window()
        sc = (win.screen() if win else None) or NSScreen.mainScreen() or NSScreen.screens()[0]
        a, b = sc.frame(), sc.visibleFrame()
        return ((a.origin.x, a.origin.y, a.size.width, a.size.height),
                (b.origin.x, b.origin.y, b.size.width, b.size.height))
    return main(f)


def make_overlay():
    """Видна на всех рабочих столах и поверх полноэкранных программ (видео, браузер на весь экран)."""
    def f():
        win = window()
        # canJoinAllSpaces | stationary | fullScreenAuxiliary
        win.setCollectionBehavior_((1 << 0) | (1 << 4) | (1 << 8))
        win.setLevel_(25)                        # NSStatusWindowLevel: выше Dock и полноэкранных окон
    main(f)


def stage_frame():
    """Рамка большого окна: весь экран до строки меню. Выше macOS окно всё равно не пускает: сдвигает вниз."""
    full, vis = screen_frames()
    return full[0], full[1], full[2], vis[1] + vis[3] - full[1]


def resize_keep_bottom_center(w, h):
    """Новый размер, ноги остаются на месте: низ и центр окна не сдвигаются."""
    def f():
        win = window()
        fr = win.frame()
        cx = fr.origin.x + fr.size.width / 2
        win.setFrame_display_(((cx - w / 2, fr.origin.y), (w, h)), True)
    main(f)


class ClickThrough:
    """Окно ловит мышку только там, где она нарисована (+ кнопка переписки). Остальное — насквозь."""

    def __init__(self, ui):
        self.ui = ui
        self.box = None             # (x0, y0, x1, y1) в точках окна, сверху-слева
        self.ignoring = False
        self.near_since = None      # с какого момента курсор рядом с ней
        self.btn = None             # левый верхний угол кнопки переписки, когда окно на весь экран
        self._fr = None
        self._fr_t = 0.0

    def _set(self, ignore: bool):
        if ignore != self.ignoring:
            self.ignoring = ignore
            main(lambda: window().setIgnoresMouseEvents_(ignore), timeout=0.3)

    def loop(self):
        if sys.platform != "darwin":
            return
        from AppKit import NSEvent
        while True:
            time.sleep(0.05)
            try:
                if not getattr(self.ui, "mini", True) or not self.box or window() is None:
                    self._set(False)
                    continue
                if NSEvent.pressedMouseButtons():       # тянут/кликают — ничего не переключаем
                    continue
                now = time.monotonic()
                if self._fr is None or now - self._fr_t > 2:       # окно стоит — незачем спрашивать 20 раз в секунду
                    self._fr, self._fr_t = frame(), now
                    self.ui.sync_stage(self._fr)
                fx, fy, fw, fh = self._fr
                m = NSEvent.mouseLocation()
                lx, ly = m.x - fx, fh - (m.y - fy)       # мышь в точках окна, сверху-слева
                x0, y0, x1, y1 = self.box
                on_her = x0 <= lx <= x1 and y0 <= ly <= y1
                if self.btn:                               # кнопка 💬 рядом с её головой
                    on_btn = self.btn[0] - 4 <= lx <= self.btn[0] + 74 and self.btn[1] - 4 <= ly <= self.btn[1] + 40
                else:
                    on_btn = lx >= fw - 50 and 0 <= ly <= 50   # кнопка 💬 в правом верхнем углу
                self._set(not (on_her or on_btn))
                near = (x0 - 80 <= lx <= x1 + 80) and (y0 - 80 <= ly <= y1 + 40)
                self.near_since = (self.near_since or time.monotonic()) if near else None
            except Exception:
                time.sleep(0.5)

    def start(self):
        threading.Thread(target=self.loop, name="clickthrough", daemon=True).start()
