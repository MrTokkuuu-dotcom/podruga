"""Отпечаток голоса: она слушает только тебя. Модель CAM++ (28 МБ, через sherpa-onnx),
работает на Mac без интернета. Запись: 3 короткие фразы → средний «отпечаток» в
data/voiceprint.npy. Каждая следующая фраза сравнивается с ним (косинусная близость).
Это фильтр, а не замок: очень похожий голос иногда может пройти."""
import io
import wave
from pathlib import Path

import numpy as np

MODEL = Path(__file__).resolve().parent / "models" / "speaker_campplus.onnx"
MODEL_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
             "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx")
NEED = 5


def _pcm(wav: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(wav)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        return a, w.getframerate()


class VoicePrint:
    def __init__(self, data_dir: Path, threshold: float = 0.32):
        import sherpa_onnx
        if not MODEL.exists():
            import urllib.request
            MODEL.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(MODEL_URL, MODEL)
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(MODEL), num_threads=1)
        self.ex = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
        self.path = Path(data_dir) / "voiceprint.npy"
        self.threshold = threshold
        self.print = np.load(self.path) if self.path.exists() else None
        self._enroll: list[np.ndarray] = []

    @property
    def active(self) -> bool:
        return self.print is not None

    def embed(self, wav: bytes) -> np.ndarray:
        a, rate = _pcm(wav)
        s = self.ex.create_stream()
        s.accept_waveform(rate, a)
        s.input_finished()
        e = np.array(self.ex.compute(s), dtype=np.float32)
        return e / (np.linalg.norm(e) + 1e-9)

    def score(self, wav: bytes) -> float:
        return float(self.embed(wav) @ self.print) if self.active else 1.0

    def is_owner(self, wav: bytes) -> tuple[bool, float]:
        s = self.score(wav)
        return s >= self.threshold, s

    def adapt(self, wav: bytes, score: float) -> None:
        """Уверенно узнала — чуть подстраивает отпечаток (микрофон, наушники, простуда)."""
        if not self.active or score < self.threshold + 0.12:
            return
        try:
            m = 0.95 * self.print + 0.05 * self.embed(wav)
            self.print = m / (np.linalg.norm(m) + 1e-9)
            self._adapted = getattr(self, "_adapted", 0) + 1
            if self._adapted % 10 == 0:
                np.save(self.path, self.print)
        except Exception:
            pass

    # --- запись ---
    def enroll_add(self, wav: bytes) -> int:
        """Добавить фразу. Возвращает, сколько ещё нужно."""
        self._enroll.append(self.embed(wav))
        if len(self._enroll) >= NEED:
            m = np.mean(self._enroll, axis=0)
            self.print = m / (np.linalg.norm(m) + 1e-9)
            np.save(self.path, self.print)
            self._enroll = []
            return 0
        return NEED - len(self._enroll)

    def forget(self) -> None:
        self.print = None
        self._enroll = []
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
