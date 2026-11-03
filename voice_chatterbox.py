"""Экспериментальный голос Chatterbox (MIT, понимает русский, эмоции, клонирование по записи).
Ставится по кнопке в отдельную папку venv_cb (~3 ГБ вместе с моделью), работает отдельным
процессом. Если медленный или сломался — она сама говорит голосом Silero."""
import base64
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

EMO_EXAGGERATION = {"joy": 0.7, "surprise": 0.8, "shy": 0.55, "tender": 0.4, "sad": 0.35,
                    "think": 0.45, "calm": 0.5}
SERVER = Path(__file__).resolve().parent / "chatterbox_server.py"


class ChatterboxVoiceOut:
    def __init__(self, home: Path, fallback=None, notify=print):
        self.home = Path(home)
        self.venv = self.home / "venv_cb"
        self.fallback = fallback          # обычно Silero (он тоже понимает эмоции)
        self.notify = notify
        self.rate = 24000
        self.proc = None
        self.ready = threading.Event()
        self.failed = False
        self.slow_strikes = 0
        self._lock = threading.Lock()
        threading.Thread(target=self._prepare, daemon=True).start()

    # --- установка и запуск ---
    def _install(self) -> bool:
        uv = self.home / "bin" / "uv"
        py = self.venv / "bin" / "python"
        fix = [str(uv), "pip", "install", "--python", str(py), "setuptools<81"]   # нужен водяному знаку
        if py.exists() and (self.venv / ".ok").exists():
            if not list((self.venv / "lib").glob("python3*/site-packages/pkg_resources")) and uv.exists():
                subprocess.run(fix, capture_output=True)
            return True
        if not uv.exists():
            self.notify("Пробный голос можно поставить только в установленном приложении.")
            return False
        self.notify("Ставлю пробный голос Chatterbox: это ~3 ГБ, 5–15 минут. Пока говорю обычным.")
        log = open(self.home / "chatterbox_install.txt", "w")
        steps = [[str(uv), "venv", "--python", "3.11", "--python-preference", "only-managed", str(self.venv)],
                 [str(uv), "pip", "install", "--python", str(py), "chatterbox-tts==0.1.7"], fix]
        for cmd in steps:
            if subprocess.run(cmd, stdout=log, stderr=log).returncode != 0:
                self.notify("Пробный голос не установился (подробности в chatterbox_install.txt).")
                return False
        (self.venv / ".ok").write_text("ok")
        return True

    def _prepare(self):
        if (self.venv / ".too_slow").exists():
            self.failed = True
            self.notify("Пробный голос на этом Mac слишком медленный — говорю обычным голосом.")
            return
        try:
            if not self._install():
                self.failed = True
                return
            first_time = not (self.venv / ".model_ok").exists()
            self.notify("Скачиваю модель пробного голоса (~2 ГБ, один раз)…" if first_time
                        else "Включаю пробный голос (около 20 секунд)…")
            self.proc = subprocess.Popen([str(self.venv / "bin" / "python"), str(SERVER)],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=open(self.home / "chatterbox_log.txt", "a"),
                                         text=True, bufsize=1)
            first = json.loads(self.proc.stdout.readline() or "{}")
            if not first.get("ready"):
                raise RuntimeError(first.get("error", "не запустился"))
            self.rate = first.get("sr", 24000)
            (self.venv / ".model_ok").write_text("ok")
            t0 = time.monotonic()
            self.proc.stdin.write(json.dumps({"text": "Привет, я тут.", "lang": "ru"}) + "\n")
            self.proc.stdin.flush()
            probe = json.loads(self.proc.stdout.readline() or "{}")
            took = time.monotonic() - t0
            dur = len(base64.b64decode(probe.get("pcm", ""))) / 2 / self.rate
            print(f"[голос] Chatterbox проверка скорости: {took:.1f} с на {dur:.1f} с речи")
            if "error" in probe or took > max(3.0, dur * 2):
                self._give_up(took, dur)
                return
            self.ready.set()
            print(f"[голос] Chatterbox готов ({first.get('device')})")
            self.notify(f"Пробный голос готов (считает на {first.get('device')}).")
        except Exception as e:
            self.failed = True
            print(f"[голос] Chatterbox: {e}")
            self.notify("Пробный голос не запустился — говорю обычным.")

    def _give_up(self, took, dur):
        self.failed = True
        (self.venv / ".too_slow").write_text(f"{took:.1f} s for {dur:.1f} s")
        try:
            self.proc.kill()
        except Exception:
            pass
        self.notify(f"Пробный голос на этом Mac слишком медленный ({took:.0f} с на фразу) — "
                    "вернулась к обычному голосу.")

    def _prompt(self) -> str | None:
        p = self.home / "models" / "my_voice.wav"     # своя запись голоса (с согласия!) — по желанию
        return str(p) if p.exists() else None

    def synth(self, text: str, emotion: str = "calm"):
        if self.failed or not self.ready.is_set() or self.slow_strikes >= 3:
            if self.fallback is not None:
                try:
                    return self.fallback.synth(text, emotion)
                except TypeError:
                    return self.fallback.synth(text), getattr(self.fallback, "rate", 24000)
            return np.zeros(0, dtype=np.int16), 24000
        with self._lock:
            req = {"text": text, "lang": "ru", "prompt": self._prompt(),
                   "exaggeration": EMO_EXAGGERATION.get(emotion, 0.5)}
            t0 = time.monotonic()
            self.proc.stdin.write(json.dumps(req) + "\n")
            self.proc.stdin.flush()
            import select
            if not select.select([self.proc.stdout], [], [], 8.0)[0]:       # ждём не дольше 8 с
                self._give_up(time.monotonic() - t0, 3.0)
                return self.synth(text, emotion)
            resp = json.loads(self.proc.stdout.readline() or '{"error": "процесс закрылся"}')
        if "error" in resp:
            print(f"[голос] Chatterbox ошибка: {resp['error']}")
            self.failed = True
            return self.synth(text, emotion)
        a = np.frombuffer(base64.b64decode(resp["pcm"]), dtype=np.int16)
        took, dur = time.monotonic() - t0, len(a) / resp["sr"]
        print(f"[голос] Chatterbox: {took:.1f} с на {dur:.1f} с речи")
        if took > max(4.0, dur * 3):              # слишком медленно для живого разговора
            self._give_up(took, dur)
        elif took > max(3.0, dur * 1.5):
            self.slow_strikes += 1
        return a, resp["sr"]
