"""Прогулки по экрану. Когда вы не заняты разговором, она спускается вниз и гуляет: по Dock —
прямо по иконкам, а где Dock'а нет — по нижнему краю экрана. Иногда присаживается, а когда засыпает —
уходит в правый угол и ложится. Говорить с ней можно и на ходу: она поворачивает голову к тебе.
Если потащить окно мышкой — сразу останавливается. Выключить: 🌸 → «Гулять по экрану»."""
import random
import subprocess
import sys
import threading
import time

SPEED = 110           # пикселей в секунду — обычный шаг
ACCEL = 260           # разгон/торможение, пикселей в секунду²
FPS = 40
LIE = (560, 260)      # окно, пока лежит


class Walker:
    def __init__(self, companion):
        self.c = companion
        self.enabled = bool(companion.cfg.get("walk", {}).get("enabled", True))
        self.busy = False
        self.sitting = False
        self.lying = False
        self._stop = threading.Event()
        self._next = time.monotonic() + random.uniform(25, 50)
        self._win = None
        self._pos = None
        self._moved_by_user = False
        self._dock = None             # (x_левый, x_правый, верх) в координатах macOS, или None
        self._dock_t = 0.0
        self._restore = None          # размер окна до того, как легла
        self._dodged = 0.0

    # ---------- главный поток macOS ----------
    def _main(self, fn):
        from PyObjCTools import AppHelper
        done, box = threading.Event(), {}

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

    def _geo(self):
        """Экран, видимая область (без Dock и меню) и рамка окна — координаты macOS (снизу-слева)."""
        def f():
            from AppKit import NSScreen
            w = self._window()
            sc = w.screen() or NSScreen.screens()[0]
            fr, vf, full = w.frame(), sc.visibleFrame(), sc.frame()
            return {"full": (full.origin.x, full.origin.y, full.size.width, full.size.height),
                    "vis": (vf.origin.x, vf.origin.y, vf.size.width, vf.size.height),
                    "win": (fr.origin.x, fr.origin.y, fr.size.width, fr.size.height)}
        return self._main(f)

    def _set(self, x, y, w=None, h=None, force=False):
        def f():
            win = self._window()
            fr = win.frame()
            o = fr.origin
            if not force and self._pos and (abs(o.x - self._pos[0]) > 4 or abs(o.y - self._pos[1]) > 4):
                self._moved_by_user = True             # её потащили мышкой
                return
            if w and h:
                win.setFrame_display_(((x, y), (w, h)), True)
            else:
                win.setFrameOrigin_((x, y))
            self._pos = (x, y)
        self._main(f)

    # ---------- где земля ----------
    def _dock_rect(self, g):
        """Где стоит Dock (если он внизу и не прячется): по окнам системы, а если не вышло —
        прикидываем по числу иконок в настройках Dock."""
        if time.monotonic() - self._dock_t < 30:
            return self._dock
        self._dock_t = time.monotonic()
        fx, fy, fw, fh = g["full"]
        vx, vy, vw, vh = g["vis"]
        dock_h = vy - fy
        if dock_h < 20:                               # Dock сбоку или прячется
            self._dock = None
            return None
        rect = None
        try:
            import Quartz
            infos = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly,
                                                      Quartz.kCGNullWindowID) or []
            for i in infos:
                if i.get("kCGWindowOwnerName") != "Dock":
                    continue
                b = i.get("kCGWindowBounds", {})
                w, h = b.get("Width", 0), b.get("Height", 0)
                if 20 < h <= dock_h + 30 and 100 < w < fw * 0.97:
                    rect = (b.get("X", 0), b.get("X", 0) + w)
                    break
        except Exception:
            pass
        if rect is None:
            try:
                tile = int(float(subprocess.run(["defaults", "read", "com.apple.dock", "tilesize"],
                                                capture_output=True, text=True).stdout.strip() or 48))
                apps = subprocess.run(["defaults", "read", "com.apple.dock", "persistent-apps"],
                                      capture_output=True, text=True).stdout.count("tile-data")
                others = subprocess.run(["defaults", "read", "com.apple.dock", "persistent-others"],
                                        capture_output=True, text=True).stdout.count("tile-data")
                n = apps + others + 2 + 3                # + Finder, корзина и недавние
                width = n * (tile + 8) + 40
                rect = (fx + (fw - width) / 2, fx + (fw + width) / 2)
            except Exception:
                rect = None
        self._dock = (rect[0], rect[1], vy) if rect else None
        return self._dock

    def ground(self, x_center, g) -> float:
        """Высота «пола» под ней: верх Dock (по иконкам) или нижний край экрана."""
        fy = g["full"][1]
        d = self._dock_rect(g)
        if d and d[0] - 10 <= x_center <= d[1] + 10:
            return d[2] - 10                          # ноги чуть ниже верха Dock — стоит на иконках
        return fy

    # ---------- условия ----------
    def _free(self) -> bool:
        c = self.c
        return (self.enabled and c.awake and not c.pauser.paused and not c.speaking
                and not c.busy.locked() and getattr(c.ui, "mini", True) and not self.lying
                and time.monotonic() - c.last_talk > 12)

    def interrupted(self) -> bool:
        c = self.c
        return (self._stop.is_set() or self._moved_by_user or not getattr(c.ui, "mini", True)
                or c.pauser.paused or not self.enabled)

    # ---------- ходьба ----------
    def walk_to(self, tx: float | None = None) -> bool:
        try:
            g = self._geo()
        except Exception as e:
            print(f"[прогулка] не вижу окно: {e}")
            return False
        vx, _, vw, _ = g["vis"]
        x, y, ww, wh = g["win"]
        x0, x1 = vx, vx + vw - ww
        if tx is None:
            for _ in range(10):
                tx = random.uniform(x0, x1)
                if abs(tx - x) > 260:
                    break
        tx = max(x0, min(x1, tx))
        self.busy, self._moved_by_user, self._pos = True, False, (x, y)
        self._stop.clear()
        self.c.ui.sit(False)
        dirn = 1 if tx > x else -1
        if abs(tx - x) > 2:                      # сначала спокойно поворачивается, потом трогается
            self.c.ui.walk(dirn, 0)
            time.sleep(0.45)
        v, sent, ok = 0.0, -1.0, False
        dt = 1 / FPS
        try:
            while not self.interrupted():
                dist = (tx - x) * dirn
                gy = self.ground(x + ww / 2, g)
                if dist <= 1 and abs(gy - y) < 1:
                    ok = True
                    break
                # разгон и плавное торможение у цели
                v_target = min(SPEED, (2 * ACCEL * max(dist, 0)) ** 0.5)
                v += max(-ACCEL * dt, min(ACCEL * dt, v_target - v))
                if dist > 0:
                    x += dirn * min(v * dt, dist)
                # на «ступеньку» Dock — плавно вверх/вниз, вниз с края — быстрее (спрыгнула)
                dy = gy - y
                y += max(-14, min(6, dy)) if abs(dy) > 0.5 else dy
                if abs(v - sent) > 8:
                    self.c.ui.walk(dirn, round(v))
                    sent = v
                self._set(x, y)
                time.sleep(dt)
        finally:
            self.c.ui.walk(0, 0)
            self.busy = False
        return ok

    def sit(self, minutes: float | None = None):
        self.busy, self.sitting = True, True
        self._stop.clear()
        self.c.ui.sit(True)
        end = time.monotonic() + (minutes or random.uniform(0.7, 2.5)) * 60
        try:
            while time.monotonic() < end and not self.interrupted() and self.c.awake:
                if self.c.busy.locked():                # заговорили — встаёт
                    break
                time.sleep(0.5)
        finally:
            self.c.ui.sit(False)
            self.sitting = False
            self.busy = False

    def stop(self):
        self._stop.set()
        if self.sitting:
            self.c.ui.sit(False)
            self.sitting = False

    # ---------- сон ----------
    def go_corner_and_sleep(self):
        if not self.enabled or sys.platform != "darwin":
            return

        def run():
            for _ in range(20):                       # пусть договорит «спокойной ночи»
                if not self.c.speaking:
                    break
                time.sleep(0.25)
            try:
                g = self._geo()
            except Exception:
                return
            vx, _, vw, _ = g["vis"]
            self._stop.clear()
            if not self.walk_to(vx + vw - g["win"][2]):
                return
            self.lie_down()
        threading.Thread(target=run, daemon=True).start()

    def lie_down(self):
        try:
            g = self._geo()
        except Exception:
            return
        x, y, w, h = g["win"]
        vx, _, vw, _ = g["vis"]
        self._restore = (w, h)
        lw, lh = getattr(self.c.ui, "lie_size", None) or LIE
        nx = min(x + w - lw + 40, vx + vw - lw)                  # прижаться к правому краю
        gy = self.ground(nx + lw / 2, g)
        self._set(nx, gy, lw, lh, force=True)
        self.lying = True
        self.c.ui.lie(True)

    def stand_up(self):
        if not self.lying:
            return
        self.lying = False
        self.c.ui.lie(False)
        try:
            g = self._geo()
            x, y, w, h = g["win"]
            rw, rh = getattr(self.c.ui, "mini_size", None) or self._restore or (250, 520)
            self._set(x + w - rw - 20, y, rw, rh, force=True)
        except Exception as e:
            print(f"[прогулка] встать: {e}")

    def wake(self):
        self.stop()
        if self.lying:
            self.stand_up()

    # ---------- куда идти ----------
    @staticmethod
    def _mouse():
        from AppKit import NSEvent
        m = NSEvent.mouseLocation()
        return m.x, m.y

    def _pick_target(self, g):
        """Не «туда-сюда по кругу», а в конкретное место: к краю экрана, к краю Dock, в свободный угол.
        Не встаёт надолго под курсором — там, скорее всего, работают."""
        vx, vy, vw, vh = g["vis"]
        x, y, ww, wh = g["win"]
        lo, hi = vx, vx + vw - ww
        spots = [lo + random.uniform(0, 80), hi - random.uniform(0, 80),
                 random.uniform(lo, hi), random.uniform(lo, hi)]
        d = self._dock_rect(g)
        if d:
            spots += [d[0] - ww / 2 + random.uniform(-40, 40), d[1] - ww / 2 + random.uniform(-40, 40)]
        try:
            mx, my = self._mouse()
        except Exception:
            mx, my = None, None
        best, best_score = None, -1e9
        for tx in spots:
            tx = max(lo, min(hi, tx))
            dist = abs(tx - x)
            score = random.uniform(0, 120)
            if dist < 180:
                score -= 400                        # слишком близко — нет смысла идти
            elif dist > vw * 0.7:
                score -= 120                        # через весь экран — редко
            if mx is not None and my < vy + vh * 0.55 and abs(tx + ww / 2 - mx) < ww / 2 + 160:
                score -= 300                        # под курсором внизу экрана — мешала бы
            if score > best_score:
                best, best_score = tx, score
        return best

    def _active_window_center(self):
        """Центр окна, в котором сейчас работают (координаты macOS, снизу-слева)."""
        import Quartz
        from AppKit import NSScreen
        full_h = NSScreen.screens()[0].frame().size.height
        for i in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly
                                                   | Quartz.kCGWindowListExcludeDesktopElements,
                                                   Quartz.kCGNullWindowID) or []:
            if i.get("kCGWindowLayer", 1) != 0:
                continue
            if i.get("kCGWindowName") == "Подруга" or i.get("kCGWindowOwnerName") in ("Подруга", "Python"):
                continue
            b = i.get("kCGWindowBounds", {})
            if b.get("Width", 0) < 200 or b.get("Height", 0) < 150:
                continue
            return b["X"] + b["Width"] / 2, full_h - (b["Y"] + b["Height"] / 2)
        return None

    def _glance_at(self, px, py, g):
        x, y, w, h = g["win"]
        fx, fy = x + w / 2, y + h * 0.85                  # где её лицо (снизу-слева)
        dx = max(-1.0, min(1.0, (px - fx) / 450))
        dy = max(-1.0, min(1.0, (fy - py) / 320))
        self.c.ui.look(dx, dy)

    def _after_arrival(self):
        """Пришла — немного побыть там: оглядеться, посмотреть, чем ты занят, потянуться или присесть."""
        if not self._free():
            return
        r = random.random()
        if r < 0.3:
            self.c.ui.idle("look", random.uniform(4, 6))         # оглядывается
        elif r < 0.5:
            try:
                p = self._active_window_center()
                if p:
                    self._glance_at(p[0], p[1], self._geo())     # смотрит на окно, где ты работаешь
            except Exception:
                pass
        elif r < 0.6:
            self.c.ui.act("stretch", 2300)
        elif r < 0.8:
            time.sleep(random.uniform(2, 5))
            if self._free():
                self.sit()

    def _cursor_close(self) -> bool:
        """Курсор уже несколько секунд крутится рядом (но не на ней) — она отходит в сторону."""
        ct = getattr(self.c.ui, "clickthrough", None)
        if not ct or not ct.near_since or not ct.ignoring:
            return False
        if time.monotonic() - ct.near_since < 3.5 or time.monotonic() - self._dodged < 25:
            return False
        if self.busy or self.sitting or self.lying or not self._free():
            return False
        self._dodged = time.monotonic()
        try:
            g = self._geo()
            mx, _ = self._mouse()
        except Exception:
            return False
        x, _, ww, _ = g["win"]
        away = -1 if mx > x + ww / 2 else 1
        print("[прогулка] курсор рядом — отхожу")
        time.sleep(0.6)                                 # сначала просто посмотрела на него
        self.walk_to(x + away * random.uniform(240, 340))
        return True

    # ---------- сама решает ----------
    def _loop(self):
        while True:
            time.sleep(0.5)
            try:
                if self._cursor_close():
                    self._next = max(self._next, time.monotonic() + 20)
                    continue
                if self.busy or time.monotonic() < self._next or not self._free():
                    continue
                if random.random() < 0.85:
                    if self.walk_to(self._pick_target(self._geo())):
                        self._after_arrival()
                else:
                    self.sit()
                self._next = time.monotonic() + random.uniform(40, 110)
            except Exception as e:
                print(f"[прогулка] {e}")
                self.busy = False
                self._next = time.monotonic() + 180

    def command(self, what: str):
        what = (what or "").lower()

        def run():
            if self.lying:
                self.stand_up()
            if what.startswith(("сес", "сид", "сяд")):
                self.sit(3)
            elif what.startswith("стоп"):
                self.stop()
            elif what.startswith("леч") or what.startswith("лож"):
                self.lie_down()
            else:
                try:
                    g = self._geo()
                except Exception:
                    return
                vx, _, vw, _ = g["vis"]
                tx = vx if "лев" in what else vx + vw - g["win"][2] if "прав" in what else None
                time.sleep(0.6)
                self._stop.clear()
                self.walk_to(tx)
        self.stop()
        time.sleep(0.1)
        threading.Thread(target=run, daemon=True).start()

    def start(self):
        if sys.platform == "darwin":
            threading.Thread(target=self._loop, name="walker", daemon=True).start()
