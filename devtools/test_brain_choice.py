"""Какой мозг отвечает и что она говорит, если думать некому. Без модели и без окна.
Запуск: PODRUGA_NO_UPDATE=1 ~/Podruga/venv/bin/python devtools/test_brain_choice.py"""
import os
import sys
import threading
from pathlib import Path

os.environ.setdefault("PODRUGA_NO_UPDATE", "1")
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import local_brain  # noqa: E402
import main  # noqa: E402
from brain import NullModel  # noqa: E402


class FakeLocal:
    def __init__(self, ever=True, failed=False):
        self.ever, self.failed = ever, failed
        self.ready = threading.Event()
        self.ready.set() if ever else None
        self.calls = []

    def unload(self): self.calls.append("unload"); return True
    def set_system(self, s): self.calls.append("set_system")


class Pauser:
    ollama = None


def comp(engine="local", google=None, local=None):
    c = main.Companion.__new__(main.Companion)
    c.cfg = {"brain": {"engine": engine}}
    c.google, c.local, c.pauser = google, local, Pauser()
    c.local_stable = lambda: "характер"
    return c


G = object()
# 1) кашлянул (голос без текста), ключа нет, свой мозг загружен — молчит, а не «скачиваю мозг»
assert comp(local=FakeLocal())._plan(wav=b"x", text=None) == (None, "unheard")
# голос без текста, есть Google — Google
assert comp(google=G, local=FakeLocal())._plan(wav=b"x", text=None) == (G, "ok")
# текст — свой мозг
c = comp(google=G, local=FakeLocal()); assert c._plan(text="привет") == (c.local, "ok")
# скриншот без ключа — честно «без Google не умею смотреть»
assert comp(local=FakeLocal())._plan(text="глянь", image=b"x") == (None, "image")
# мозг ещё качается, ключа нет
assert comp(local=FakeLocal(ever=False))._plan(text="привет") == (None, "downloading")
# мозг не встал, ключа нет — не врёт про скачивание
assert comp(local=FakeLocal(ever=False, failed=True))._plan(text="привет") == (None, "failed")
# свой мозг выгружен (спала) и грузится ~10 с: если есть Google — отвечает он, чтобы не ждать
sleepy = FakeLocal(); sleepy.ready.clear()
assert comp(google=G, local=sleepy)._plan(text="привет") == (G, "ok")
c = comp(local=sleepy); assert c._plan(text="привет") == (sleepy, "ok"), "без ключа — ждём свой"
# проснулась: сначала новый характер (дата в памяти могла смениться), потом загрузка — один пересчёт, а не два
order = []
sleepy.set_system = lambda s: order.append("set_system")
sleepy.preload = lambda *a: order.append("preload")
c = comp(local=sleepy); c._wake_local(sync=True)
assert order == ["set_system", "preload"], order
lines = {w: main.Companion._error_line(main.NotReady(w)) for w in ("image", "downloading", "failed", "nokey")}
assert "скачива" in lines["downloading"] and "скачива" not in lines["failed"] and "экран" in lines["image"]

# 3) выбрал Google — модель выгружается, пауза в игре её больше не грузит, кэш характера не пересчитывается
loc = FakeLocal(); c = comp(engine="google", google=G, local=loc); c.pauser.ollama = loc
c._stop_local(); c._sync_local()
assert "unload" in loc.calls and "set_system" not in loc.calls and isinstance(c.pauser.ollama, NullModel)

# 4) свой мозг только на Mac с чипом Apple и памятью от 16 ГБ, и если есть место (или модель уже скачана)
GB = 1024 ** 3
assert local_brain.can_run(Path("/nonexistent"), machine="arm64", memsize=16 * GB, free=50 * GB)[0]
assert not local_brain.can_run(Path("/nonexistent"), machine="arm64", memsize=8 * GB, free=50 * GB)[0]
assert not local_brain.can_run(Path("/nonexistent"), machine="x86_64", memsize=32 * GB, free=50 * GB)[0]
assert not local_brain.can_run(Path("/nonexistent"), machine="arm64", memsize=16 * GB, free=3 * GB)[0]
print("OK")
