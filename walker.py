"""Прогулки по экрану. Когда вы не заняты разговором, она спускается вниз и гуляет: по Dock —
прямо по иконкам, а где Dock'а нет — по нижнему краю экрана. Иногда присаживается, а когда засыпает —
уходит в правый угол и ложится. Говорить с ней можно и на ходу: она поворачивает голову к тебе.
Если потащить её мышкой — сразу останавливается. Выключить: 🌸 → «Гулять по экрану».

Окно одно, на весь экран, и не двигается: движение считает 3D-страница в том же кадре, в котором рисует,
поэтому шаг и перемещение идут ровно вместе. Здесь только решаем, куда и когда идти."""
import random
import subprocess
import sys
import threading
import time

BODY_W = 220          # ширина её тела в пикселях: столько нужно места, чтобы не упереться в край экрана
CORNER = 80           # запас от края экрана: лёжа она занимает больше места


class Walker:
    def __init__(self, companion):
        self.c = companion
        self.enabled = bool(companion.cfg.get("walk", {}).get("enabled", True))
        self.busy = False
        self.sitting = False
        self.lying = False
        self._stop = threading.Event()
        self._done = threading.Event()
        self._next = time.monotonic() + random.uniform(25, 50)
        self._moved_by_user = False
        self._dock = None             # (x_левый, x_правый, верх) в координатах macOS, или None
        self._dock_t = 0.0
        self._dodged = 0.0

    # ---------- где она и где земля ----------
    def _geo(self):
        """Экран, видимая область (без Dock и меню) и её место — координаты macOS (снизу-слева).
        Окно одно на весь экран и не двигается, поэтому win — воображаемая рамка вокруг неё."""
        import winctl
        full, vis = winctl.screen_frames()
        hx, hy = self.c.ui.her_pos
        h = getattr(self.c.ui, "mini_size", (0, 520))[1]
        return {"full": full, "vis": vis, "win": (full[0] + hx - BODY_W / 2, full[1] + hy, BODY_W, h)}

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

    def _send_ground(self, g):
        """Рассказать окну, где «пол» повыше: верх Dock (ноги чуть ниже верха — стоит на иконках)."""
        d = self._dock_rect(g)
        fx, fy = g["full"][0], g["full"][1]
        if d:
            self.c.ui.ground(d[0] - fx, d[1] - fx, d[2] - fy - 10)
        else:
            self.c.ui.ground(None, None, None)

    # ---------- условия ----------
    def _free(self) -> bool:
        c = self.c
        return (self.enabled and getattr(c.ui, "stage_on", False) and c.awake and not c.pauser.paused and not c.speaking
                and not c.busy.locked() and getattr(c.ui, "mini", True) and not self.lying
                and time.monotonic() - c.last_talk > 12)

    def interrupted(self) -> bool:
        c = self.c
        return (self._stop.is_set() or self._moved_by_user or not getattr(c.ui, "mini", True)
                or c.pauser.paused or not self.enabled)

    # ---------- ходьба ----------
    def walk_to(self, tx: float | None = None) -> bool:
        """Идти к точке. Само движение считает окно в каждом кадре, здесь только ждём, пока дойдёт."""
        if not getattr(self.c.ui, "stage_on", False):
            return False
        try:
            g = self._geo()
        except Exception as e:
            print(f"[прогулка] не вижу экран: {e}")
            return False
        vx, _, vw, _ = g["vis"]
        x, _, ww, _ = g["win"]
        x0, x1 = vx, vx + vw - ww
        if tx is None:
            for _ in range(10):
                tx = random.uniform(x0, x1)
                if abs(tx - x) > 260:
                    break
        tx = max(x0, min(x1, tx))
        self.busy, self._moved_by_user = True, False
        self._stop.clear()
        self._done.clear()
        self.c.ui.sit(False)
        self._send_ground(g)
        self.c.ui.walk_to(tx + ww / 2 - g["full"][0])
        deadline = time.monotonic() + abs(tx - x) / 120 + 8     # с запасом: сначала встаёт и поворачивается
        ok = False
        try:
            while not self.interrupted() and time.monotonic() < deadline:
                if self._done.wait(0.1):
                    ok = True
                    break
            if not ok:
                self.c.ui.walk_stop()
        finally:
            self.busy = False
        return ok

    def arrived(self):
        self._done.set()

    def user_moved(self):
        self._moved_by_user = True
        self._done.clear()

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
    def begin_sleep(self) -> bool:
        """Позвать ДО того, как она станет «спящей»: иначе глаза закроются сразу, ещё на ногах."""
        if not (self.enabled and sys.platform == "darwin" and getattr(self.c.ui, "stage_on", False)
                and getattr(self.c.ui, "mini", True)):
            return False
        self.c.ui.sleep_seq("drowsy")
        return True

    def go_corner_and_sleep(self):
        """Зевает и трёт глаза → идёт в угол с открытыми глазами → садится → ложится → глаза закрываются."""
        def still_sleeping():
            return not self.c.awake

        def run():
            for _ in range(20):                       # пусть договорит «спокойной ночи»
                if not self.c.speaking:
                    break
                time.sleep(0.25)
            if not still_sleeping():
                return
            self.c.ui.sleep_seq("yawn")
            for _ in range(42):
                time.sleep(0.1)
                if not still_sleeping():
                    return
            try:
                g = self._geo()
            except Exception:
                g = None
            if g:
                vx, _, vw, _ = g["vis"]
                self._stop.clear()
                self.walk_to(vx + vw - g["win"][2] - CORNER)
            if not still_sleeping():
                return
            self.lying = True
            self.c.ui.sleep_seq("down")
        threading.Thread(target=run, daemon=True).start()

    def lie_down(self):
        self.lying = True
        self.c.ui.lie(True)

    def stand_up(self):
        if not self.lying:
            return
        self.lying = False
        self.c.ui.lie(False)

    def wake(self):
        self.stop()
        self.lying = False
        self.c.ui.sleep_seq("cancel")

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
                self.walk_to(tx)
        self.stop()
        time.sleep(0.1)
        threading.Thread(target=run, daemon=True).start()

    def start(self):
        if sys.platform == "darwin":
            threading.Thread(target=self._loop, name="walker", daemon=True).start()
