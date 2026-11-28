"""Живой голос девочки: Qwen3-TTS 0.6B (Apache 2.0) на видеочипе Mac через mlx-audio (MIT).
Голос задаётся образцом из voice_refs/ — синтетическим, придуманным моделью по описанию (чужих прав нет).
Один голос на русском, английском и корейском. ~0,7 с на короткую фразу, ~2× быстрее реального времени.

Вся работа с моделью — в своём потоке (MLX не любит, когда видеочип дёргают из разных потоков)."""
import importlib
import os
import queue
import re
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

MODEL_REPO = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit"
PKGS = ["mlx==0.32.4", "mlx-audio==0.6.7"]
STAMP = ".voice_qwen_failed"
REFS = Path(__file__).resolve().parent / "voice_refs"
REF_TEXT = "Привет! Я так рада, что ты вернулся. Как прошёл твой день? А я тут без тебя немножко заскучала."
VOICES = ("anya", "alisa", "tanya")
RATE = 24000


def lang_name(text: str) -> str:
    if re.search(r"[가-힣ᄀ-ᇿ㄰-㆏]", text):
        return "korean"
    if re.search(r"[А-Яа-яЁё]", text):
        return "russian"
    if re.search(r"[A-Za-z]", text):
        return "english"
    return "russian"


class PhraseCache:
    """Короткие фразы, которые она уже говорила этим голосом («Включила!», «Вот, открыла.», «Привет, Дима.»),
    лежат готовым звуком: в следующий раз — сразу, без работы видеочипа (он нужен мозгу). ~100 КБ на фразу,
    не больше MAX штук (самые старые уходят)."""
    MAX_CHARS, MAX = 60, 400

    def __init__(self, folder: Path):
        self.dir = folder
        self.hits = 0

    def _path(self, voice: str, text: str) -> Path:
        import hashlib
        key = re.sub(r"\s+", " ", text.strip().lower())
        return self.dir / voice / (hashlib.sha1(key.encode("utf-8")).hexdigest()[:20] + ".npy")

    def get(self, voice: str, text: str):
        if len(text.strip()) > self.MAX_CHARS:
            return None
        f = self._path(voice, text)
        try:
            a = np.load(f)
            os.utime(f)                                   # свежая — дольше живёт
            self.hits += 1
            return a
        except Exception:
            return None

    def put(self, voice: str, text: str, audio: np.ndarray) -> None:
        if len(text.strip()) > self.MAX_CHARS or audio is None or len(audio) < RATE // 4:
            return
        try:
            f = self._path(voice, text)
            f.parent.mkdir(parents=True, exist_ok=True)
            np.save(f, audio.astype(np.int16))
            files = sorted(f.parent.glob("*.npy"), key=lambda x: x.stat().st_mtime)
            for old in files[:-self.MAX]:
                old.unlink(missing_ok=True)
        except Exception as e:
            print(f"[голос] кэш фраз: {e}", flush=True)


class QwenVoiceOut:
    def __init__(self, home: Path, voice: str = "anya", fallback=None, notify=print):
        self.home = Path(home)
        self.dir = self.home / "models" / "tts" / MODEL_REPO.split("/")[-1]
        self.voice = voice if voice in VOICES else "anya"
        self.fallback = fallback            # пока качается/не встал — говорит прежний голос
        self.notify = notify
        self.rate = RATE
        self.ready = threading.Event()
        self.failed = False
        self.model = None
        self._refs: dict = {}
        self.cache = PhraseCache(self.home / "data" / "voice_cache")
        self._jobs: queue.Queue = queue.Queue()
        threading.Thread(target=self._worker, name="voice-qwen", daemon=True).start()

    def synth(self, text: str, emotion: str = "calm") -> tuple[np.ndarray, int]:
        if not self.ready.is_set():
            if self.fallback is not None:
                r = self.fallback.synth(text, emotion) if _takes_emotion(self.fallback) else self.fallback.synth(text)
                return r if isinstance(r, tuple) else (r, getattr(self.fallback, "rate", RATE))
            return np.zeros(0, dtype=np.int16), RATE
        hit = self.cache.get(self.voice, text)
        if hit is not None:
            return hit, RATE
        out: queue.Queue = queue.Queue()
        self._jobs.put((text, self.voice, out))
        try:
            kind, val = out.get(timeout=60)
        except queue.Empty:
            return np.zeros(0, dtype=np.int16), RATE
        if kind == "err":
            print(f"[голос] Qwen: ошибка ({val})", flush=True)
            return np.zeros(0, dtype=np.int16), RATE
        return val, RATE

    def synth_stream(self, text: str, emotion: str = "calm"):
        """По кусочкам (~1 с речи): первый звук через ~0,7 с, пока она говорит — готовится следующий."""
        if not self.ready.is_set():
            yield self.synth(text, emotion)
            return
        hit = self.cache.get(self.voice, text)
        if hit is not None:                               # уже говорила эту фразу — готовый звук, сразу
            print(f"[голос] готовая фраза: «{text[:40]}»", flush=True)
            yield hit, RATE
            return
        out: queue.Queue = queue.Queue()
        cancel = threading.Event()
        self._jobs.put((text, self.voice, out, cancel))
        try:
            while True:
                try:
                    kind, val = out.get(timeout=60)
                except queue.Empty:
                    return
                if kind == "chunk":
                    yield val, RATE
                elif kind == "err":
                    print(f"[голос] Qwen: ошибка ({val})", flush=True)
                    return
                else:
                    return
        finally:
            cancel.set()                         # перебили — дальше не озвучиваем

    # ---------- свой поток ----------
    def _worker(self):
        try:
            self._load()
        except Exception as e:
            self.failed = True
            print(f"[голос] живой голос не включился: {e} — говорю прежним", flush=True)
            return
        while True:
            job = self._jobs.get()
            text, voice, out = job[:3]
            try:
                if len(job) == 4:
                    parts = []
                    for a in self._stream(text, voice, job[3]):
                        parts.append(a)
                        out.put(("chunk", a))
                    whole = not job[3].is_set()              # до «end»: потом слушатель сам ставит cancel
                    out.put(("end", None))
                    if parts and whole:
                        self.cache.put(voice, text, np.concatenate(parts))
                else:
                    a = self._synth(text, voice)
                    self.cache.put(voice, text, a)
                    out.put(("ok", a))
            except Exception as e:
                out.put(("err", e))

    def _install(self) -> bool:
        uv = self.home / "bin" / "uv"
        if os.environ.get("PODRUGA_BUNDLED") or not uv.exists():
            return False
        stamp = self.home / STAMP
        if stamp.exists() and stamp.read_text().strip() == " ".join(PKGS):
            return False
        print("[голос] ставлю живой голос (mlx-audio)…", flush=True)
        r = subprocess.run([str(uv), "pip", "install", "--python", sys.executable, "-q", *PKGS],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[голос] живой голос не встал:\n{r.stderr[-800:]}", flush=True)
            stamp.write_text(" ".join(PKGS))
            return False
        return True

    def _load(self):
        try:
            importlib.import_module("mlx_audio")
        except ImportError:
            if not self._install():
                raise RuntimeError("mlx-audio недоступен")
            importlib.invalidate_caches()
        import mlx.core as mx
        from mlx_audio.tts.utils import load_model
        self._mx = mx
        if not (self.dir / "config.json").exists() or not any(self.dir.glob("*.safetensors")):
            self.notify("Качаю живой голос (~2 ГБ, один раз). Пока говорю прежним.")
            from huggingface_hub import snapshot_download
            self.dir.mkdir(parents=True, exist_ok=True)
            snapshot_download(MODEL_REPO, local_dir=str(self.dir))
            self.notify("Живой голос готов.")
        t0 = time.monotonic()
        self.model = load_model(str(self.dir))
        self._synth("Привет.", self.voice)                     # прогрев: первая настоящая фраза — сразу
        print(f"[голос] живой голос ({self.voice}) готов за {time.monotonic() - t0:.1f} с", flush=True)
        self.ready.set()

    def _ref(self, voice: str):
        if voice not in self._refs:
            with wave.open(str(REFS / f"{voice}.wav"), "rb") as w:
                a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
            self._refs[voice] = self._mx.array(a)              # один и тот же массив — модель кэширует разбор образца
        return self._refs[voice]

    def _stream(self, text: str, voice: str, cancel: threading.Event):
        import gpu
        gpu.mark_own()
        t0, first, n = time.monotonic(), None, 0
        for r in self.model.generate(text=text, lang_code=lang_name(text), ref_audio=self._ref(voice),
                                     ref_text=REF_TEXT, stream=True, streaming_interval=1.0):
            if cancel.is_set():
                break
            a = _i16(r.audio)
            first = first or time.monotonic() - t0
            n += len(a)
            yield a
        print(f"[голос] Qwen: первый звук {first or 0:.2f} с, {time.monotonic() - t0:.2f} с на {n / RATE:.1f} с речи",
              flush=True)

    def _synth(self, text: str, voice: str) -> np.ndarray:
        import gpu
        gpu.mark_own()
        t0 = time.monotonic()
        # кусочками, как в потоке: целиком звук разбирается разом и память подскакивает на ~4 ГБ (замер v37)
        chunks = [np.array(r.audio) for r in self.model.generate(
            text=text, lang_code=lang_name(text), ref_audio=self._ref(voice), ref_text=REF_TEXT,
            stream=True, streaming_interval=1.0)]
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        a16 = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        print(f"[голос] Qwen: {time.monotonic() - t0:.2f} с на {len(a16) / RATE:.1f} с речи", flush=True)
        return a16


def _i16(audio) -> np.ndarray:
    return (np.clip(np.array(audio), -1, 1) * 32767).astype(np.int16)


def _takes_emotion(v) -> bool:
    import inspect
    try:
        return len(inspect.signature(v.synth).parameters) >= 2
    except (TypeError, ValueError):
        return False
