"""Уши на компьютере: микрофон + фильтр речи (бесплатно, без ИИ).
Фильтр — нейросеть Silero VAD (2 МБ, MIT): отличает живой голос от музыки, видео, шума
и стука клавиатуры гораздо лучше простой проверки громкости.
Отдаёт только готовые фразы в формате WAV — в облако уходит только то, что ты сказал."""
import collections
import io
import queue
import threading
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

RATE = 16000
MODEL = Path(__file__).resolve().parent / "models" / "silero_vad.onnx"


def to_wav(frames: list[bytes]) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(frames))
    return buf.getvalue()


def level(frame: bytes) -> float:
    return float(np.abs(np.frombuffer(frame, dtype=np.int16)).mean())


class SileroVAD:
    """Вероятность, что в кусочке 32 мс звучит человеческая речь (0..1)."""
    FRAME = 512
    CONTEXT = 64

    def __init__(self, model_path: Path = MODEL):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = ort.InferenceSession(str(model_path), sess_options=opts,
                                            providers=["CPUExecutionProvider"])
        self.reset()

    def reset(self) -> None:
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, self.CONTEXT), dtype=np.float32)

    def prob(self, frame: bytes) -> float:
        x = (np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0)[None, :]
        inp = np.concatenate([self.context, x], axis=1)
        out, self.state = self.session.run(None, {
            "input": inp, "state": self.state, "sr": np.array(RATE, dtype=np.int64)})
        self.context = inp[:, -self.CONTEXT:]
        return float(out[0][0])


class WebrtcVAD:
    """Запасной фильтр, если Silero не загрузился."""
    FRAME = 480

    def __init__(self, level_: int = 3):
        import webrtcvad
        self.vad = webrtcvad.Vad(level_)

    def reset(self) -> None:
        pass

    def prob(self, frame: bytes) -> float:
        return 1.0 if self.vad.is_speech(frame, RATE) else 0.0


def make_vad():
    try:
        return SileroVAD()
    except Exception as e:
        print(f"[уши] Silero VAD не загрузился ({e}), беру простой фильтр.")
    try:
        return WebrtcVAD()
    except Exception:
        return None


class Listener:
    def __init__(self, energy_threshold: float = 300, min_speech_ms: int = 500,
                 end_silence_ms: int = 700, max_phrase_s: int = 20, device=None,
                 speech_prob: float = 0.6, min_density: float = 0.45, on_level=None,
                 on_speech=None, barge_ms: int = 350):
        self.vad = make_vad()
        self.frame = self.vad.FRAME if self.vad else 512
        self.frame_ms = self.frame * 1000 // RATE
        self.energy_threshold = energy_threshold
        self.speech_prob = speech_prob      # насколько уверенно «это голос»
        self.min_density = min_density      # доля речи во фразе: у музыки она рваная
        self.min_speech_ms = min_speech_ms
        self.end_silence_ms = end_silence_ms
        self.max_ms = max_phrase_s * 1000
        self.device = device
        self.on_level = on_level or (lambda v: None)
        # вызывается сразу, как только ты уверенно заговорил (~0.35 с) — для перебивания
        self.on_speech = on_speech or (lambda: None)
        self.barge_frames = max(1, barge_ms // self.frame_ms)
        self.q: queue.Queue[bytes] = queue.Queue()
        self.phrase_q: queue.Queue[bytes] = queue.Queue()
        self.muted = False
        self.stream = None

    def _callback(self, indata, frames, time_info, status):
        if not self.muted:
            self.q.put(bytes(indata))

    def start(self) -> None:
        self.stream = sd.RawInputStream(samplerate=RATE, blocksize=self.frame, dtype="int16",
                                        channels=1, callback=self._callback, device=self.device)
        self.stream.start()
        # слух работает в своём потоке: даже пока она отвечает, он слышит, что ты заговорил
        threading.Thread(target=self._worker, name="ears", daemon=True).start()

    def mute(self) -> None:
        self.muted = True

    def unmute(self) -> None:
        while not self.q.empty():  # выбрасываем то, что успело попасть, пока она говорила
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        if self.vad:
            self.vad.reset()
        self.muted = False

    def _is_speech(self, frame: bytes) -> bool:
        lvl = level(frame)
        self.on_level(lvl)
        if lvl <= self.energy_threshold:
            return False
        return self.vad is None or self.vad.prob(frame) >= self.speech_prob

    def phrases(self):
        """Бесконечный генератор фраз (WAV-байты)."""
        while True:
            yield self.phrase_q.get()

    def _worker(self):
        for wav in self._detect():
            self.phrase_q.put(wav)

    def _detect(self):
        pre = max(1, 300 // self.frame_ms)         # 300 мс до начала речи, чтобы не обрезать слово
        start_need = max(1, 150 // self.frame_ms)  # ~150 мс уверенной речи — начали
        ring = collections.deque(maxlen=pre)
        voiced: list[bytes] = []
        triggered, silence_ms, speech_frames, last_speech_idx = False, 0, 0, 0
        while True:
            frame = self.q.get()
            if len(frame) != self.frame * 2:
                continue
            speech = self._is_speech(frame)
            if not triggered:
                ring.append((frame, speech))
                if sum(s for _, s in ring) >= start_need:
                    triggered = True
                    voiced = [f for f, _ in ring]
                    speech_frames = sum(s for _, s in ring)
                    last_speech_idx = len(voiced)
                    silence_ms = 0
                    ring.clear()
                continue
            voiced.append(frame)
            if speech:
                speech_frames += 1
                silence_ms = 0
                last_speech_idx = len(voiced)
                if speech_frames == self.barge_frames:
                    try:
                        self.on_speech()
                    except Exception as e:
                        print(f"[уши] {e}")
            else:
                silence_ms += self.frame_ms
            if silence_ms >= self.end_silence_ms or len(voiced) * self.frame_ms >= self.max_ms:
                density = speech_frames / max(1, last_speech_idx)
                if speech_frames * self.frame_ms >= self.min_speech_ms and density >= self.min_density:
                    yield to_wav(voiced)
                elif speech_frames * self.frame_ms >= self.min_speech_ms:
                    print(f"   (похоже на музыку/шум, пропускаю: речи {density:.0%})")
                triggered, voiced, speech_frames = False, [], 0


HEADPHONE_WORDS = ("airpods", "headphone", "наушник", "buds", "beats", "earpods", "headset",
                   "гарнитур", "wh-", "wf-", "jabra", "bose", "sony", "jbl", "galaxy")
SPEAKER_WORDS = ("speaker", "динамик", "macbook", "built-in", "встроен", "display", "монитор", "hdmi")


def output_device_name() -> str:
    try:
        return str(sd.query_devices(kind="output")["name"])
    except Exception:
        return ""


def output_is_headphones() -> bool:
    """По названию устройства вывода: наушники или колонки. Сомневаемся — считаем колонками
    (тогда перебивание выключено, и она точно не перебьёт сама себя)."""
    name = output_device_name().lower()
    if any(w in name for w in SPEAKER_WORDS):
        return False
    return any(w in name for w in HEADPHONE_WORDS)
