"""Вся программа целиком, но вместо микрофона — заранее записанные фразы (синтез Silero),
отпечаток голоса выключен. Временная папка вместо ~/Podruga/data: память Димы не трогаем."""
import io
import os
import queue
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

REPO, TMPHOME = sys.argv[1], Path(sys.argv[2])
REAL = Path.home() / "Podruga"
TMPHOME.mkdir(parents=True, exist_ok=True)
for name in ("models", "bin", ".env", "avatar.vrm", "avatars"):          # ключ читает сама программа, на экран он не выводится
    if not (TMPHOME / name).exists():
        os.symlink(REAL / name, TMPHOME / name)
os.environ["PODRUGA_HOME"] = str(TMPHOME)
os.environ["PODRUGA_NO_UPDATE"] = "1"
os.chdir(REPO)
sys.path.insert(0, REPO)
sys.dont_write_bytecode = True

import torch  # noqa: E402
tts = torch.package.PackageImporter(str(REAL / "models/silero_v5_6_ru.pt")).load_pickle("tts_models", "model")


def wav_of(text, gap_end=0.9):
    a = tts.apply_tts(text=text, speaker="aidar", sample_rate=48000).numpy()[::3] * 0.5
    a = np.concatenate([np.zeros(4000), a, np.zeros(int(16000 * gap_end))])
    pcm = (np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes()
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm)
    return b.getvalue()


SCRIPT = []
WAVS = [(wav_of(t), pause, t) for t, pause in SCRIPT]

import audio_in  # noqa: E402


class FakeListener:
    def __init__(self, *a, **k):
        self.q, self.stream, self.phrase_end, self.muted = queue.Queue(), None, None, False

    def start(self):
        pass

    def mute(self):
        self.muted = True

    def unmute(self):
        self.muted = False

    def phrases(self):
        time.sleep(10)
        import subprocess
        for g, o in (("alisa", "street"), ("tanya", "formal"), ("anya", "default")):
            r = COMP.ui.api.set_avatar(g, o)
            print(f"\n>>> переодеваю: {g}/{o} → {r} | имя теперь: {COMP.cfg.get('companion_name')}", flush=True)
            time.sleep(14)
            ok = COMP.ui.window.evaluate_js("!!(window.VRM3D && VRM3D.ready)")
            st = COMP.ui.window.evaluate_js("document.body.classList.contains('stage')")
            print(f">>> модель загружена: {ok}, окно на весь экран: {st}", flush=True)
            subprocess.run(["screencapture", "-x", f"{sys.argv[2]}/../shots/live_{g}_{o}.png"])
        for wav, pause, text in WAVS:
            print(f"\n>>> говорю: «{text}»", flush=True)
            self.phrase_end = time.monotonic()
            yield wav
            time.sleep(pause)
        print("\n>>> ПРОВЕРКА ОКОНЧЕНА", flush=True)
        time.sleep(4)
        threading.Thread(target=lambda: COMP.quit_now("проверка"), daemon=True).start()
        time.sleep(30)


audio_in.Listener = FakeListener
import main  # noqa: E402
main.logsetup.setup()
cfg = main.load_config()
COMP = main.Companion(cfg)
COMP.voiceprint = None                                  # синтетический голос — не голос Димы
COMP.run()
