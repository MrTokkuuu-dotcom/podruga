"""Голос. Живой голос девочки (Qwen3-TTS, voice_qwen.py); запасные — Silero и Piper, пока живой качается.
Пока она произносит одно предложение, следующее уже озвучивается."""
import queue
import re
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
    qwen — живой голос девочки (по умолчанию), silero и piper — запасные."""

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
        self.qwen = None
        self.lang = "ru"
        self.piper_en = None
        self.korean = None
        self._korean_failed = False
        self._notify = print
        self.apply()

    # --- английский голос (и для практики языка, и для английских фраз) ---
    def set_lang(self, lang: str):
        self.lang = lang
        if lang == "en":
            self.set_lang_voice_en()

    def set_lang_voice_en(self):
        if self.piper_en is None and not getattr(self, "_en_loading", False):
            self._en_loading = True
            self._en_ready = threading.Event()
            threading.Thread(target=self._load_en, daemon=True).start()

    def prepare(self, lang: str):
        """Услышали фразу на этом языке — готовим голос заранее, пока думает Google (первая фраза без задержки)."""
        if self._qwen_ready():
            return                                          # живой голос и так говорит на всех трёх языках
        if lang == "en":
            self.set_lang_voice_en()
        elif lang == "ko" and self.korean is None and not self._korean_failed:
            def warm():
                ko = self._korean()
                if ko is not None:
                    ko.synth("응")                          # разогрев: первая настоящая фраза — сразу
            threading.Thread(target=warm, daemon=True).start()

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
        finally:
            self._en_ready.set()

    # окно подставляет сюда показ сообщений в переписке
    @property
    def notify(self):
        return self._notify

    @notify.setter
    def notify(self, fn):
        self._notify = fn
        for v in (self.silero, self.qwen):
            if v is not None:
                v.notify = fn

    def apply(self):
        """Применить текущие настройки (движок, голос, тон)."""
        v = self.cfg["voice"]
        self.engine = v.get("engine", "qwen")
        qwen_on_disk = (self.home / "models" / "tts" / "Qwen3-TTS-12Hz-0.6B-Base-8bit" / "config.json").exists()
        if self.engine not in ("qwen", "silero", "piper"):
            self.engine = "qwen"                            # старые облачные/пробные голоса больше не бывают
        if self.engine == "silero" or (self.engine == "qwen" and not qwen_on_disk):
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
                if self.engine == "silero":
                    self.engine = "piper"
        if self.engine == "qwen":
            try:
                if self.qwen is None:
                    from voice_qwen import QwenVoiceOut
                    self.qwen = QwenVoiceOut(self.home, voice=v.get("qwen_voice", "anya"),
                                             fallback=self.silero or self.piper, notify=self._notify)
                self.qwen.voice = v.get("qwen_voice", "anya")
            except Exception as e:
                print(f"[голос] живой голос не включился ({e}), говорю прежним.")
                self.engine = "silero" if self.silero is not None else "piper"
        print(f"[голос] движок: {self.engine}")

    # --- голос по языку самой фразы: русские буквы — русский, корейские — корейский, только латиница — английский.
    # Раньше выбор шёл по «режиму», и английский голос читал русский текст по буквам.
    @staticmethod
    def script_of(text: str) -> str:
        if re.search(r"[\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f]", text):
            return "ko"
        if re.search(r"[А-Яа-яЁё]", text):
            return "ru"
        if re.search(r"[A-Za-z]", text):
            return "en"
        return "ru"

    def _korean(self):
        if self.korean is None and not self._korean_failed:
            try:
                from voice_korean import KoreanVoiceOut
                self.korean = KoreanVoiceOut()
            except Exception as e:
                self._korean_failed = True
                print(f"[голос] корейского голоса нет: {e}")
        return self.korean

    def _qwen_ready(self) -> bool:
        return self.engine == "qwen" and self.qwen is not None and self.qwen.ready.is_set()

    def synth_stream(self, text: str, emotion: str = "calm"):
        """По кусочкам — для живого голоса (первый звук ~0,7 с); остальные голоса — одним куском."""
        if self._qwen_ready():
            yield from self.qwen.synth_stream(text, emotion)
        else:
            yield self.synth(text, emotion)

    def synth(self, text: str, emotion: str = "calm"):
        if self._qwen_ready():                              # один живой голос на всех трёх языках
            return self.qwen.synth(text, emotion)
        lang = self.script_of(text)
        if lang == "ko":
            ko = self._korean()
            if ko is not None:
                return ko.synth(text), ko.rate
        if lang == "en" and len(re.findall(r"[A-Za-z]+", text)) >= 2:
            if self.piper_en is None:
                self.set_lang_voice_en()                    # загружается — подождём чуть-чуть (~1 с), а не читаем русским
                self._en_ready.wait(6 if (self.home / "models" / "en_US-amy-medium.onnx").exists() else 0)
            if self.piper_en is not None:
                return self.piper_en.synth(text), self.piper_en.rate
        if self.engine == "silero" and self.silero is not None:
            return self.silero.synth(text, emotion)
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
        self.on_amp = on_amp or (lambda *a: None)          # громкость для движения рта
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

    def _stream(self, text: str, emotion: str, gen: int) -> None:
        """Живой голос по кусочкам: первый кусок играет сразу, остальные доозвучиваются, пока она говорит.
        Мягкий вход у первого куска; после фразы — короткая пауза (голос сам заканчивается тишиной)."""
        first = True
        for audio, rate in self.voice.synth_stream(text, emotion):
            if gen != self._gen:
                return
            a = resample(audio, rate)
            if not len(a):
                continue
            if first:
                f = min(int(OUT_RATE * FADE_MS / 1000), len(a) // 2)
                a = a.astype(np.float32)
                a[:f] *= np.linspace(0.0, 1.0, f, dtype=np.float32)
                a = a.astype(np.int16)
                first = False
            self.audio_q.put((gen, a))
        if not first and gen == self._gen:
            self.audio_q.put((gen, np.zeros(int(OUT_RATE * GAP_MS / 1000), dtype=np.int16)))

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
                        if hasattr(self.voice, "synth_stream"):
                            self._stream(text, emo, gen)
                        else:
                            audio = self._synth(text, emo)
                            if gen != self._gen:
                                break          # пока озвучивали — её перебили
                            self.audio_q.put((gen, audio))
                        if gen != self._gen:
                            break
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
                        try:
                            from visemes import shape
                            self.on_amp(min(1.0, rms / 5000.0), shape(piece, OUT_RATE))
                        except TypeError:
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
