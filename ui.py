"""Окно приложения: героиня, статус, переписка, кнопки, настройки, ввод ключа.
pywebview (на Mac — встроенный WebKit). Окно без рамки, поверх других, таскается за шапку."""
import json
import queue
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

HTML = Path(__file__).resolve().parent / "avatar" / "app.html"
FULL = (360, 600)     # с перепиской
MINI = (250, 520)     # только она (по умолчанию) — во весь рост

VOICES = [("xenia", "Ксения — мягкая (бесплатно, на Mac)"), ("kseniya", "Ксюша — звонкая (бесплатно)"),
          ("baya", "Бая — спокойная (бесплатно)"),
          ("Sulafat", "Облако: тёплый (лимиты Google)"), ("Leda", "Облако: юный"),
          ("Aoede", "Облако: воздушный"), ("Achernar", "Облако: мягкий"),
          ("chatterbox", "Проба: Chatterbox — живее, но тяжёлый (~3 ГБ)")]
PITCHES = [("medium", "обычный"), ("high", "повыше"), ("x-high", "высокий")]


class NullUI:
    """Без окна (текстовый режим или если окно не открылось)."""
    enabled = False
    def state(self, s): pass
    def add(self, role, text, tag=None): pass
    def her(self, text): pass
    def her_done(self): pass
    def emotion(self, e, hold=None): pass
    def look(self, dx, dy): pass
    def mouth(self, v, shape=None): pass
    mini = True
    stage_on = False
    her_pos = (0, 0)
    def ground(self, a, b, h): pass
    def walk_to(self, x): pass
    def walk_stop(self): pass
    def sit(self, on): pass
    def lie(self, on): pass
    def sleep_seq(self, kind): pass
    def gesture(self, name, sec=None): pass
    def ledges(self, items): pass
    def jump_to(self, x, y, support): pass
    def sit_edge(self, on): pass
    def act(self, name, ms=None): pass
    def idle(self, name, sec=4): pass
    def outfit(self, o): pass
    def show_chat(self): pass
    def hide_now(self): pass
    visible = True
    def toggle_visible(self): pass
    def ensure_visible(self): pass
    def open_settings(self): pass
    def geometry(self): return None
    def level(self, v): pass
    def title(self, name): pass
    def need_key(self, msg=None): pass
    def key_ok(self): pass
    def run(self, worker): worker()
    def close(self): pass


class Api:
    """Методы, которые вызывает окно (кнопки). Компаньон подставляется после запуска."""

    def __init__(self, ui):
        self._ui = ui
        self._companion = None

    def _bg(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def ui_ready(self):
        self._ui._on_ready()

    def send_text(self, text):
        if self._companion:
            self._bg(self._companion.on_text, text)

    def look(self):
        if self._companion:
            self._bg(self._companion.on_look_button)

    def toggle_sleep(self):
        if self._companion:
            self._bg(self._companion.toggle_sleep)

    def touch(self, zone):
        if self._companion and zone in ("head", "face", "body", "dropped"):
            self._bg(self._companion.on_touch, zone)

    def fit(self, w, h, lie_w=None, lie_h=None):
        """3D-модель сообщила реальные размеры: окно «только она» — по ним (с запасом под руки)."""
        try:
            w, h = int(w), int(h)
            if not (200 <= w <= 900 and 300 <= h <= 1000):
                return
            self._ui.mini_size = (w, h)
            if lie_w and lie_h:
                self._ui.lie_size = (int(lie_w), int(lie_h))
            import winctl
            if getattr(self._ui, "mini", True):
                if sys.platform == "darwin":
                    self._ui.enter_stage(to_floor=True)
                else:
                    winctl.resize_keep_bottom_center(w, h)
            print(f"[окно] размер по модели: {w}×{h}")
        except Exception as e:
            print(f"[окно] fit: {e}")

    def hitbox(self, x0, y0, x1, y1, hx=None, hy=None, bx=None, by=None):
        ct = getattr(self._ui, "clickthrough", None)
        if ct:
            ct.box = (float(x0), float(y0), float(x1), float(y1))
            ct.btn = (float(bx), float(by)) if (hx is not None and bx is not None) else None
        if hx is not None:
            self._ui.her_pos = (float(hx), float(hy))

    def walk_done(self, ok=True):
        wk = self._companion and getattr(self._companion, "walker", None)
        if wk:
            wk.arrived()

    def landed(self, support=None):
        """Приземлилась после прыжка: support — id края окна или None (пол)."""
        wk = self._companion and getattr(self._companion, "walker", None)
        if wk:
            wk.landed(support)

    def moved(self):
        """Её потащили мышкой."""
        wk = self._companion and getattr(self._companion, "walker", None)
        if wk:
            wk.user_moved()

    def toggle_pause(self):
        if self._companion:
            self._bg(self._companion.pauser.toggle)

    def set_key(self, key):
        if not self._companion:
            return {"ok": False, "msg": "Ещё загружаюсь, попробуй через пару секунд"}
        return self._companion.try_key(key)

    def get_settings(self):
        if not self._companion:
            return None
        c = self._companion.cfg
        v = c["voice"]
        eng = v.get("engine")
        cur = ("chatterbox" if eng == "chatterbox" else
               v.get("silero_speaker", "xenia") if eng == "silero" else v["gemini_voice"])
        return {"companion_name": c["companion_name"], "user_name": c["user_name"],
                "voice": cur, "style": v.get("style", ""), "pitch": v.get("silero_pitch", "medium"),
                "voices": VOICES, "pitches": PITCHES, "has_key": self._companion.has_key(),
                "traits": c.get("traits", {}),
                "voiceprint": bool(self._companion.voiceprint and self._companion.voiceprint.active)}

    def save_settings(self, values):
        if not self._companion:
            return {"ok": False}
        self._companion.update_settings(values)
        return {"ok": True}

    def preview_voice(self, voice, pitch="medium"):
        if self._companion:
            self._bg(self._companion.preview_voice, voice, pitch)

    def enroll_voice(self):
        if self._companion:
            self._bg(self._companion.start_enroll)

    def forget_voice(self):
        if self._companion:
            self._bg(self._companion.forget_voice)

    def open_url(self, url):
        if url.startswith("https://aistudio.google.com/"):
            webbrowser.open(url)

    def open_data(self):
        if self._companion and sys.platform == "darwin":
            subprocess.run(["open", str(self._companion.cfg["_data_dir"])])

    def compact(self, on):
        """Переключение «только она» ↔ «с перепиской». Нижний край окна остаётся на месте,
        чтобы она не прыгала по экрану."""
        w, h = (getattr(self._ui, "mini_size", None) or MINI) if on else FULL
        self._ui.mini = bool(on)
        wk = self._companion and getattr(self._companion, "walker", None)
        if wk and wk.lying:                     # открыли переписку, пока лежала — встаёт
            wk.lying = False
            self._ui.lie(False)
        if sys.platform == "darwin":
            try:
                self._ui.leave_stage(w, h) if not on else self._ui.enter_stage()
                return
            except Exception as e:
                print(f"[окно] compact: {e}")
        win = self._ui.window
        try:
            x, y = win.x, win.y
            ow, oh = win.width, win.height
            win.resize(w, h)
            win.move(max(0, x + (ow - w) // 2), max(0, y + oh - h))
        except Exception:
            try:
                win.resize(w, h)
            except Exception:
                pass

    def menu(self):
        try:
            import menubar
            menubar.popup()
        except Exception as e:
            print(f"[меню] {e}")

    def quit(self):
        if self._companion:
            self._bg(self._companion.quit_now)
        else:
            import os
            os._exit(0)


class AppUI:
    enabled = True

    def __init__(self):
        import webview
        self.webview = webview
        self.api = Api(self)
        self.ready = False
        self.stage_on = False          # окно на весь экран, она ходит внутри него
        self.her_pos = (0.0, 0.0)          # где она: x центра и y ног, пиксели окна снизу-слева
        self._queue: list[str] = []
        self._lock = threading.Lock()
        self._outbox: queue.Queue = queue.Queue()
        self._busy_since = None
        self._dispatcher = threading.Thread(target=self._dispatch_loop, name="ui-dispatch",
                                            daemon=True)
        self._dispatcher.start()
        threading.Thread(target=self._watch_dispatcher, daemon=True).start()
        self.window = webview.create_window(
            "Подруга", self._page_url(), js_api=self.api, width=MINI[0], height=MINI[1],
            frameless=True, easy_drag=False, on_top=True, transparent=True, resizable=False,
            background_color="#000000")

    # --- доставка вызовов в окно ---
    # Все обращения к окну идут через ОДИН отдельный поток с очередью. Компаньон кладёт
    # команду и сразу идёт дальше: окно больше никогда не может «подвесить» голос.
    def _on_ready(self):
        with self._lock:
            self.ready = True
            pending, self._queue = self._queue, []
        for js in pending:
            self._outbox.put(js)

    @staticmethod
    def _page_url() -> str:
        """Есть 3D-модель (~/Podruga/avatar.vrm) — кладём рядом со страницей и открываем через
        локальный сервер pywebview (по file:// браузер не даёт загрузить модель). Нет — как раньше."""
        try:
            from config import HOME
            import shutil
            src, dst = Path(HOME) / "avatar.vrm", HTML.parent / "model.vrm"
            if not src.exists():                    # своей модели нет — общая из обновления
                src = HTML.parent / "default.vrm"
            if src.exists():
                if not dst.exists() or dst.stat().st_size != src.stat().st_size \
                        or dst.stat().st_mtime < src.stat().st_mtime:
                    shutil.copy2(src, dst)
                print(f"[окно] 3D-модель: {src.name}")
                return str(HTML)
            if dst.exists():
                dst.unlink()
        except Exception as e:
            print(f"[окно] 3D-модель не подключилась: {e}")
        return HTML.as_uri()

    def _call(self, fn: str, *args):
        js = f"ui.{fn}({', '.join(json.dumps(a, ensure_ascii=False) for a in args)})"
        with self._lock:
            if not self.ready:
                self._queue.append(js)
                return
        self._outbox.put(js)

    def _dispatch_loop(self):
        me = threading.current_thread()
        while self._dispatcher is me:
            js = self._outbox.get()
            if js is None:
                continue
            self._busy_since = time.monotonic()
            try:
                self.window.run_js(js)
            except Exception as e:
                print(f"[окно] {str(e)[:120]}")
            finally:
                self._busy_since = None

    def _watch_dispatcher(self):
        """Если окно не ответило за 5 с — бросаем зависший вызов и запускаем новый поток."""
        while True:
            time.sleep(1)
            t = self._busy_since
            if t and time.monotonic() - t > 5:
                print("[окно] не отвечает 5 с — пропускаю команду, работаю дальше")
                self._busy_since = None
                self._dispatcher = threading.Thread(target=self._dispatch_loop,
                                                    name="ui-dispatch", daemon=True)
                self._dispatcher.start()

    # --- что умеет окно ---
    def state(self, s): self._call("state", s)
    def add(self, role, text, tag=None): self._call("add", role, text, tag)
    def her(self, text): self._call("appendHer", text)
    def her_done(self): self._call("closeHer")
    def emotion(self, e, hold=None): self._call("emotion", e, hold)
    def title(self, name): self._call("title", name)
    def need_key(self, msg=None): self._call("needKey", msg)
    def key_ok(self): self._call("keyOk")

    def _fast(self, js: str):
        """Частые мелкие обновления (громкость, взгляд, рот): если окно не успевает — кадр пропускаем."""
        if self.ready and self._outbox.qsize() < 2 and self._busy_since is None:
            self._outbox.put(js)

    def level(self, v): self._fast(f"ui.level({int(v)})")
    def look(self, dx, dy): self._fast(f"ui.look({dx:.2f},{dy:.2f})")
    def mouth(self, v, shape=None):
        self._fast(f"ui.mouth({v:.2f},'{shape or ''}')")
    def act(self, name, ms=None): self._call("act", name, ms)
    def idle(self, name, sec=4): self._call("idle", name, sec)
    mini = True
    def ground(self, a, b, h): self._call("ground", a, b, h)
    def walk_to(self, x): self._call("walkTo", float(x))
    def walk_stop(self): self._call("walkStop")
    def sleep_seq(self, kind): self._call("sleepSeq", kind)
    def gesture(self, name, sec=None): self._call("gesture", name, sec)
    def ledges(self, items): self._call("ledges", items)
    def jump_to(self, x, y, support): self._call("jumpTo", float(x), float(y), support)
    def sit_edge(self, on): self._call("sitEdge", bool(on))
    def sit(self, on): self._call("sit", bool(on))
    def lie(self, on): self._call("lie", bool(on))
    def outfit(self, o): self._call("outfit", o)
    def show_chat(self): self._call("showChat")

    def hide_now(self):
        """Спрятать окно сразу, не дожидаясь очереди команд (при выходе)."""
        if sys.platform == "darwin":
            import winctl
            winctl.main(lambda: winctl.window().orderOut_(None), timeout=0.3)
        else:
            self.window.hide()

    # --- большое окно: накрывает экран, не двигается, клики проходят насквозь мимо неё ---
    def enter_stage(self, to_floor=False):
        import winctl
        x, y, w, h = winctl.frame()
        full, vis = winctl.screen_frames()
        hx = x + w / 2 - full[0]
        hy = max(0.0, y - full[1])
        if to_floor:                                 # при запуске — на Dock или на нижний край экрана
            hy = max(0.0, vis[1] - full[1] - 10)
        hx = max(110.0, min(full[2] - 110.0, hx))
        fr = winctl.stage_frame()
        winctl.set_frame(*fr)
        try:
            winctl.make_overlay()
        except Exception as e:
            print(f"[окно] поверх полноэкранных: {e}")
        self.her_pos = (hx, hy)
        self.stage_on = True
        self._call("stage", True, fr[2], fr[3], hx, hy)

    def leave_stage(self, w, h):
        """Открыли переписку: обычное окно там, где она стоит."""
        import winctl
        full, vis = winctl.screen_frames()
        hx, hy = self.her_pos
        x = max(vis[0], min(vis[0] + vis[2] - w, full[0] + hx - w / 2))
        y = max(vis[1], min(vis[1] + vis[3] - h, full[1] + hy))
        self.stage_on = False
        self._call("stage", False)
        ct = getattr(self, "clickthrough", None)
        if ct:
            ct.btn = None
            ct._fr = None
        winctl.set_frame(x, y, w, h)

    def sync_stage(self, fr):
        """Сменилось разрешение экрана или подключили монитор — снова накрыть весь экран."""
        if not (self.stage_on and getattr(self, "mini", True)):
            return
        import winctl
        want = winctl.stage_frame()
        if tuple(fr) != tuple(want):
            winctl.set_frame(*want)
            self._call("stage", True, want[2], want[3], min(self.her_pos[0], want[2] - 110.0), self.her_pos[1])
            ct = getattr(self, "clickthrough", None)
            if ct:
                ct._fr = None

    def open_settings(self):
        with self._lock:
            if self.ready:
                self._outbox.put("openSettings()")

    visible = True

    def toggle_visible(self):
        self.ensure_visible() if not self.visible else self._set_visible(False)

    def ensure_visible(self):
        if not self.visible:
            self._set_visible(True)

    def _set_visible(self, on: bool):
        try:
            self.window.show() if on else self.window.hide()
            self.visible = on
        except Exception as e:
            print(f"[окно] show/hide: {e}")

    def geometry(self):
        """(x, y, ширина, высота) окна; координаты сверху-слева экрана."""
        try:
            if self.stage_on:                         # окно на весь экран — важно, где стоит она сама
                import winctl
                full, _ = winctl.screen_frames()
                mw, mh = getattr(self, "mini_size", MINI)
                return (full[0] + self.her_pos[0] - mw / 2, full[3] - self.her_pos[1] - mh, mw, mh)
            w = self.window
            return w.x, w.y, w.width, w.height
        except Exception:
            return None

    def run(self, worker):
        """Окно живёт в главном потоке (так требует macOS), компаньон — в фоновом."""
        self.webview.start(worker)

    def close(self):
        try:
            self.window.destroy()
        except Exception:
            pass


def make_ui(cfg: dict):
    if not cfg.get("avatar", {}).get("enabled", True):
        return NullUI()
    try:
        return AppUI()
    except Exception as e:
        print(f"⚠ Окно не открылось ({e}). Работаю без него.")
        return NullUI()
