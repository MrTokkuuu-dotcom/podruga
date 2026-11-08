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
CORNER = 230          # запас от края экрана: лёжа вдоль экрана голова уходит к углу


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
        self.support = None           # id окна, на верхнем крае которого она стоит (None — на полу/Dock)
        self._landed = threading.Event()
        self._ledges = []             # [[id, x0, x1, y], …] в пикселях окна, y — от низа
        self._ledges_key = ""
        self._ledges_t = 0.0
        self._on_ledge_since = 0.0
        self._typed_dodge = 0.0

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

    # ---------- окна на экране ----------
    def _windows(self, g):
        """Обычные окна других программ (спереди назад): (id, pid, x0, y0, x1, y1) в пикселях нашего окна, y снизу."""
        import os
        import Quartz
        from AppKit import NSScreen
        main_h = NSScreen.screens()[0].frame().size.height
        fx, fy, fw, fh = g["full"]
        out = []
        for i in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly
                                                   | Quartz.kCGWindowListExcludeDesktopElements,
                                                   Quartz.kCGNullWindowID) or []:
            if i.get("kCGWindowLayer", 1) != 0 or i.get("kCGWindowOwnerPID") == os.getpid():
                continue
            if float(i.get("kCGWindowAlpha", 1)) < 0.2:
                continue
            b = i.get("kCGWindowBounds", {})
            w, h = b.get("Width", 0), b.get("Height", 0)
            if w < 240 or h < 120:
                continue
            x0 = b["X"] - fx
            top = (main_h - b["Y"]) - fy                    # верх окна в координатах macOS → от низа экрана
            out.append((int(i.get("kCGWindowNumber", 0)), i.get("kCGWindowOwnerPID"), x0, top - h, x0 + w, top))
        return out

    def _compute_ledges(self, g):
        """Верхние края окон, которые не закрыты другими окнами и над которыми есть место для неё."""
        wins = self._windows(g)
        H = g["full"][3]
        ledges = []
        for k, (wid, _, x0, y0, x1, y1) in enumerate(wins):
            if y1 > H - 560 or y1 < 120:                   # у самой строки меню ей не встать, у пола — незачем
                continue
            free = [(x0, x1)]
            for (_, _, a0, b0, a1, b1) in wins[:k]:          # окна спереди закрывают часть края
                if b0 - 4 <= y1 <= b1 + 300:                 # перекрывают сам край или место над ним
                    nxt = []
                    for s0, s1 in free:
                        if a1 <= s0 or a0 >= s1:
                            nxt.append((s0, s1))
                            continue
                        if a0 > s0:
                            nxt.append((s0, a0))
                        if a1 < s1:
                            nxt.append((a1, s1))
                    free = nxt
            for n, (s0, s1) in enumerate(free):
                if s1 - s0 >= 260:
                    ledges.append([wid * 10 + n, round(s0), round(s1), round(y1)])
        return ledges

    def update_ledges(self, force=False):
        if not getattr(self.c.ui, "stage_on", False):
            return
        if not force and time.monotonic() - self._ledges_t < 1.5:
            return
        self._ledges_t = time.monotonic()
        try:
            ledges = self._compute_ledges(self._geo())
        except Exception as e:
            print(f"[окна] {e}")
            return
        key = repr(ledges)
        if key != self._ledges_key:
            self._ledges_key, self._ledges = key, ledges
            self.c.ui.ledges(ledges)
            if self.support is not None and not any(l[0] == self.support for l in ledges):
                self.support = None                       # окно пропало — она спрыгнет сама

    def landed(self, support):
        self.support = support
        if support is not None:
            self._on_ledge_since = time.monotonic()
        self._landed.set()

    def jump_to(self, cx: float, y: float, support) -> bool:
        """Прыгнуть: cx — центр по горизонтали, y — высота ног (пиксели окна)."""
        self._landed.clear()
        self.busy = True
        try:
            self.c.ui.jump_to(cx, y, support)
            ok = self._landed.wait(4)
        finally:
            self.busy = False
        return ok

    def climb(self) -> bool:
        """Залезть на край окна: подойти под него и запрыгнуть. Потом посидеть на краю или походить по нему."""
        g = self._geo()
        hx, hy = self.c.ui.her_pos
        fx = g["full"][0]
        good = [l for l in self._ledges if 110 <= l[3] - hy <= 430]
        if not good:
            return False
        l = random.choice(good)
        cx = min(max(hx, l[1] + 80), l[2] - 80) if l[1] + 80 < l[2] - 80 else (l[1] + l[2]) / 2
        if abs(cx - hx) > 6:
            if not self.walk_to(cx - BODY_W / 2 + fx):
                return False
        print(f"[окна] запрыгиваю на окно (высота {l[3]} пикс)")
        if not self.jump_to(cx, l[3], l[0]):
            return False
        time.sleep(0.4)
        if random.random() < 0.6 and self._free():
            self.sit(edge=True)
        return True

    def jump_down(self) -> bool:
        if self.support is None:
            return False
        g = self._geo()
        hx, _ = self.c.ui.her_pos
        l = next((l for l in self._ledges if l[0] == self.support), None)
        side = -1 if (l and hx - l[1] < l[2] - hx) else 1
        target = (l[1] - 90 if side < 0 else l[2] + 90) if l else hx
        target = max(110.0, min(g["full"][2] - 110.0, target))
        floor_y = 0.0
        d = self._dock_rect(g)
        if d and d[0] - g["full"][0] <= target <= d[1] - g["full"][0]:
            floor_y = d[2] - g["full"][1] - 10
        print("[окна] спрыгиваю вниз")
        return self.jump_to(target, floor_y, None)

    def _typing_window(self, g):
        """Окно, в котором ты сейчас печатаешь: (x0, y0, x1, y1) или None."""
        from reactions import idle_seconds
        if idle_seconds() > 1.5:
            return None
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        pid = app.processIdentifier() if app else None
        for (_, wpid, x0, y0, x1, y1) in self._windows(g):
            if wpid == pid:
                return x0, y0, x1, y1
        return None

    def _dodge_typing(self) -> bool:
        """Стоит перед окном, где ты печатаешь, — отходит в сторону (или спрыгивает с него)."""
        if self.busy or self.sitting or self.lying or not self._free() or time.monotonic() - self._typed_dodge < 30:
            return False
        g = self._geo()
        w = self._typing_window(g)
        if not w:
            return False
        hx, hy = self.c.ui.her_pos
        x0, y0, x1, y1 = w
        her = (hx - 90, hy, hx + 90, hy + 470)
        on_top_of_it = self.support is not None and abs(hy - y1) < 6
        if on_top_of_it or her[2] < x0 or her[0] > x1 or her[3] < y0 + 30 or her[1] > y1 - 30:
            return False
        self._typed_dodge = time.monotonic()
        W_ = g["full"][2]
        left, right = x0 - 120, x1 + 120
        cands = [c for c in (left, right) if 110 <= c <= W_ - 110]
        if not cands:
            return False
        cx = min(cands, key=lambda c: abs(c - hx))
        print("[окна] ты печатаешь — отхожу от окна")
        if self.support is not None:
            return self.jump_to(cx, 0.0, None)
        return self.walk_to(cx - BODY_W / 2 + g["full"][0])

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

    def sit(self, minutes: float | None = None, edge: bool = False):
        self.busy, self.sitting = True, True
        self._stop.clear()
        if edge and self.support is not None:
            self.c.ui.sit_edge(True)                      # на краю окна, свесив ноги
        else:
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
                if self.support is not None:
                    self.jump_down()
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
                self.update_ledges()
                if self._dodge_typing():
                    self._next = max(self._next, time.monotonic() + 30)
                    continue
                if self._cursor_close():
                    self._next = max(self._next, time.monotonic() + 20)
                    continue
                if self.busy or time.monotonic() < self._next or not self._free():
                    continue
                if self.support is not None and (time.monotonic() - self._on_ledge_since > 240 or random.random() < 0.35):
                    self.jump_down()                          # погуляла по окну — пора вниз
                elif self.support is None and self._ledges and random.random() < 0.3:
                    self.climb()                              # залезть на окно
                elif random.random() < 0.85:
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
