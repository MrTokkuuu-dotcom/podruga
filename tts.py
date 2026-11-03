"""Голос. По умолчанию — Silero (бесплатно, на Mac), по желанию — облако Gemini, запасной — Piper.
Пока она произносит одно предложение, следующее уже озвучивается."""
import queue
import threading

import numpy as np


class PiperVoiceOut:
    def __init__(self, model_path: str, speed: float = 1.0):
        from piper import PiperVoice
        from piper.config import SynthesisConfig
        self.voice = PiperVoice.load(model_path)
        self.rate = self.voice.config.sample_rate
        self.syn = SynthesisConfig(length_scale=1.0 / speed)

    def synth(self, text: str) -> np.ndarray:
        chunks = [c.audio_int16_array for c in self.voice.synthesize(text, syn_config=self.syn)]
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)


class VoiceRouter:
    """Все голоса в одном месте, переключаются на лету из настроек:
    silero — бесплатно на Mac (по умолчанию), gemini — облако, piper — простой запасной."""

    def __init__(self, cfg: dict, root, home):
        self.cfg, self.home = cfg, home
        v = cfg["voice"]
        self.piper = None
        piper_path = root / v["model"]
        if piper_path.exists():
            try:
                self.piper = PiperVoiceOut(str(piper_path), v.get("speed", 1.0))
            except Exception as e:
                print(f"[голос] Piper не загрузился: {e}")
        self.rate = self.piper.rate if self.piper else 24000
        self.silero = None
        self.gemini = None
        self.chatterbox = None
        self.lang = "ru"
        self.piper_en = None
        self._notify = print
        self.apply()

    # --- английский голос для практики языка ---
    def set_lang(self, lang: str):
        self.lang = lang
        if lang == "en" and self.piper_en is None:
            threading.Thread(target=self._load_en, daemon=True).start()

    def _load_en(self):
        import subprocess
        import sys
        d = self.home / "models"
        d.mkdir(parents=True, exist_ok=True)
        model = d / "en_US-amy-medium.onnx"
        try:
            if not model.exists():
                self._notify("Скачиваю английский голос (один раз)…")
                subprocess.run([sys.executable, "-m", "piper.download_voices", "en_US-amy-medium",
                                "--data-dir", str(d)], check=True, capture_output=True, timeout=300)
            self.piper_en = PiperVoiceOut(str(model), 1.0)
            print("[голос] английский голос готов")
        except Exception as e:
            print(f"[голос] английский голос не загрузился: {e}")

    # окно подставляет сюда показ сообщений в переписке
    @property
    def notify(self):
        return self._notify

    @notify.setter
    def notify(self, fn):
        self._notify = fn
        for v in (self.silero, self.gemini, getattr(self, "chatterbox", None)):
            if v is not None:
                v.notify = fn

    def apply(self):
        """Применить текущие настройки (движок, голос, тон)."""
        v = self.cfg["voice"]
        self.engine = v.get("engine", "silero")
        if self.engine in ("silero", "chatterbox"):
            try:
                if self.silero is None:
                    from voice_silero import SileroVoiceOut
                    self.silero = SileroVoiceOut(self.home / "models", fallback=self.piper,
                                                 notify=self._notify)
                self.silero.speaker = v.get("silero_speaker", "xenia")
                self.silero.pitch = v.get("silero_pitch", "medium")
                self.silero.speed = v.get("silero_rate", "medium")
            except Exception as e:
                print(f"[голос] Silero недоступен ({e}), говорю запасным.")
                self.engine = "piper"
        if self.engine == "chatterbox":
            try:
                if getattr(self, "chatterbox", None) is None:
                    from voice_chatterbox import ChatterboxVoiceOut
                    self.chatterbox = ChatterboxVoiceOut(self.home, fallback=self.silero,
                                                         notify=self._notify)
            except Exception as e:
                print(f"[голос] Chatterbox не включился ({e}), говорю Silero.")
                self.engine = "silero"
        elif self.engine == "gemini":
            try:
                if self.gemini is None:
                    from voice_gemini import GeminiVoiceOut
                    self.gemini = GeminiVoiceOut(v["gemini_model"], v["gemini_voice"],
                                                 v.get("style", ""), self.piper)
                    self.gemini.notify = self._notify
                self.gemini.voice_name = v["gemini_voice"]
                self.gemini.style = v.get("style", "")
            except Exception as e:
                print(f"[голос] Gemini TTS не включился ({e}).")
                self.engine = "piper"
        print(f"[голос] движок: {self.engine}")

    def synth(self, text: str, emotion: str = "calm"):
        if self.lang == "en" and self.piper_en is not None:
            return self.piper_en.synth(text), self.piper_en.rate
        if self.engine == "chatterbox" and getattr(self, "chatterbox", None) is not None:
            return self.chatterbox.synth(text, emotion)
        if self.engine == "silero" and self.silero is not None:
            return self.silero.synth(text, emotion)
        if self.engine == "gemini" and self.gemini is not None:
            return self.gemini.synth(text)
        if self.piper:
            return self.piper.synth(text), self.piper.rate
        return np.zeros(0, dtype=np.int16), 24000


def make_voice(cfg: dict, root, home=None):
    return VoiceRouter(cfg, root, home or root)


OUT_RATE = 24000     # одна частота для всего звука — без пересоздания потока и щелчков
FADE_MS = 12         # плавное начало и конец каждой фразы
GAP_MS = 90          # короткая естественная пауза между предложениями


def resample(audio: np.ndarray, src: int, dst: int = OUT_RATE) -> np.ndarray:
    if src == dst or not len(audio):
        return audio
    n = int(round(len(audio) * dst / src))
    x = np.linspace(0, len(audio) - 1, n)
    return np.interp(x, np.arange(len(audio)), audio.astype(np.float32)).astype(np.int16)


def smooth(audio: np.ndarray, rate: int = OUT_RATE) -> np.ndarray:
    """Убирает щелчки на стыках: мягкий вход/выход и пауза после фразы."""
    a = audio.astype(np.float32)
    f = min(int(rate * FADE_MS / 1000), len(a) // 2)
    if f > 0:
        ramp = np.linspace(0.0, 1.0, f, dtype=np.float32)
        a[:f] *= ramp
        a[-f:] *= ramp[::-1]
    gap = np.zeros(int(rate * GAP_MS / 1000), dtype=np.float32)
    return np.clip(np.concatenate([a, gap]), -32768, 32767).astype(np.int16)


class Speaker:
    """Очередь фраз: speak() возвращается сразу, wait_done() ждёт, пока всё прозвучит.
    Звук идёт в ОДИН постоянно открытый поток: раньше на каждую фразу он открывался
    заново — отсюда были треск и «скрежет» на стыках."""

    def __init__(self, voice, on_talk=None, on_text=None, on_amp=None):
        self.voice = voice
        self.on_amp = on_amp or (lambda v: None)          # громкость для движения рта
        self.on_talk = on_talk or (lambda talking: None)  # для анимации рта
        self.on_text = on_text or (lambda text: None)     # для переписки в окне
        self.text_q: queue.Queue[str] = queue.Queue()
        self.audio_q: queue.Queue = queue.Queue()
        self._gen = 0              # «поколение» речи: stop() увеличивает, старое не играется
        threading.Thread(target=self._synth_loop, daemon=True).start()
        threading.Thread(target=self._play_loop, daemon=True).start()

    def speak(self, text: str, emotion: str = "calm") -> None:
        print(f"🗣  {text}")
        self.on_text(text)
        self.text_q.put((text, emotion))

    def wait_done(self) -> None:
        self.text_q.join()
        self.audio_q.join()

    def stop(self) -> None:
        """Замолчать сразу (перебивание): выбросить очередь и оборвать текущую фразу."""
        self._gen += 1
        for q in (self.text_q, self.audio_q):
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
                q.task_done()

    def _synth(self, text: str, emotion: str = "calm") -> np.ndarray:
        try:
            out = self.voice.synth(text, emotion)
        except TypeError:                       # голос без эмоций (Piper, облако)
            out = self.voice.synth(text)
        audio, rate = out if isinstance(out, tuple) else (out, self.voice.rate)
        return smooth(resample(audio, rate))

    def _synth_loop(self):
        while True:
            first = self.text_q.get()
            gen = self._gen
            items = [first if isinstance(first, tuple) else (first, "calm")]
            # если уже ждут ещё предложения с той же эмоцией — озвучиваем вместе
            while True:
                try:
                    nxt = self.text_q.get_nowait()
                except queue.Empty:
                    break
                items.append(nxt if isinstance(nxt, tuple) else (nxt, "calm"))
            try:
                if self.voice:
                    groups: list[tuple[str, str]] = []
                    for text, emo in items:
                        if groups and groups[-1][1] == emo:
                            groups[-1] = (groups[-1][0] + " " + text, emo)
                        else:
                            groups.append((text, emo))
                    for text, emo in groups:
                        audio = self._synth(text, emo)
                        if gen != self._gen:
                            break              # пока озвучивали — её перебили
                        self.audio_q.put((gen, audio))
            except Exception as e:
                print(f"[голос] ошибка озвучки: {e}")
            finally:
                for _ in items:
                    self.text_q.task_done()

    def _open_stream(self):
        import sounddevice as sd
        # latency='high' — запас буфера, чтобы звук не рвался, когда процессор занят
        stream = sd.OutputStream(samplerate=OUT_RATE, channels=1, dtype="int16",
                                 latency="high", blocksize=1024)
        stream.start()
        return stream

    def _play_loop(self):
        stream = None
        chunk = OUT_RATE * 6 // 100                # по 0.06 с: рот успевает за речью, и можно оборвать
        while True:
            item = self.audio_q.get()
            gen, audio = item if isinstance(item, tuple) else (self._gen, item)
            try:
                if len(audio) and gen == self._gen:
                    if stream is None:
                        stream = self._open_stream()
                    self.on_talk(True)
                    for i in range(0, len(audio), chunk):
                        if gen != self._gen:
                            break
                        piece = audio[i:i + chunk]
                        rms = float(np.sqrt(np.mean(piece.astype(np.float32) ** 2))) if len(piece) else 0.0
                        self.on_amp(min(1.0, rms / 5000.0))
                        stream.write(piece.reshape(-1, 1))
            except Exception as e:
                print(f"[голос] ошибка воспроизведения: {e}")
                try:
                    stream and stream.close()
                except Exception:
                    pass
                stream = None   # откроем заново на следующей фразе (например, сменились наушники)
            finally:
                if self.audio_q.qsize() == 0:
                    self.on_amp(0.0)
                    self.on_talk(False)
                try:
                    self.audio_q.task_done()
                except ValueError:
                    pass        # stop() уже отметил её выполненной
