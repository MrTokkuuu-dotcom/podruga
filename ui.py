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
    def walk(self, d, px=0): pass
    def sit(self, on): pass
    def lie(self, on): pass
    def act(self, name, ms=None): pass
    def outfit(self, o): pass
    def show_chat(self): pass
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
                "voiceprint": bool(self._companion.voiceprint and self._companion.voiceprint.active),
                "telegram": self._companion.telegram_status()}

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

    def set_telegram(self, token):
        if not self._companion:
            return {"ok": False}
        return self._companion.setup_telegram(token)

    def telegram_unpair(self):
        tg = self._companion and getattr(self._companion, "tg", None)
        if tg:
            tg.unpair()
            return self._companion.telegram_status()
        return {"on": False}

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
        w, h = MINI if on else FULL
        self._ui.mini = bool(on)
        wk = self._companion and getattr(self._companion, "walker", None)
        if wk and wk.lying:                     # открыли переписку, пока лежала — встаёт
            wk.lying = False
            self._ui.lie(False)
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
        self._ui.close()


class AppUI:
    enabled = True

    def __init__(self):
        import webview
        self.webview = webview
        self.api = Api(self)
        self.ready = False
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
    mini = True
    def walk(self, d, px=0): self._call("walk", int(d), int(px))
    def sit(self, on): self._call("sit", bool(on))
    def lie(self, on): self._call("lie", bool(on))
    def outfit(self, o): self._call("outfit", o)
    def show_chat(self): self._call("showChat")

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
