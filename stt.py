"""Распознавание речи прямо на Mac (faster-whisper). В Google уходит уже текст, а не запись:
запрос легче и быстрее, лимит тратится меньше, а готовые ответы срабатывают чаще.
Модель (~480 МБ, «small») скачивается один раз в ~/Podruga/models/whisper. Если что-то не так —
она по-старому отправляет в Google саму запись."""
import io
import threading
import time
import wave
from pathlib import Path

import numpy as np

# Известные «галлюцинации» Whisper на тишине и шуме (особенно по-русски)
JUNK = ("субтитры", "продолжение следует", "редактор субтитров", "dimatorzok", "спасибо за просмотр",
        "подписывайтесь", "ставьте лайки", "amara.org", "сделано с любовью", "корректор")


class WhisperSTT:
    def __init__(self, home: Path, model: str = "small", notify=print):
        self.dir = Path(home) / "models" / "whisper"
        self.name = model
        self.notify = notify
        self.model = None
        self.ready = threading.Event()
        self.failed = False
        self.last_secs = 0.0
        self._lock = threading.Lock()
        threading.Thread(target=self._load, name="whisper-load", daemon=True).start()

    def _load(self):
        try:
            from faster_whisper import WhisperModel
            first = not any(self.dir.glob("**/model.bin"))
            if first:
                self.notify("Скачиваю распознавание речи для Mac (~480 МБ, один раз). Пока слушаю по-старому.")
            self.dir.mkdir(parents=True, exist_ok=True)
            t0 = time.monotonic()
            self.model = WhisperModel(self.name, device="cpu", compute_type="int8",
                                      download_root=str(self.dir), cpu_threads=0)   # 0 = все ядра
            # прогрев: первая фраза иначе медленная
            self.model.transcribe(np.zeros(16000, dtype=np.float32), language="ru")
            print(f"[уши] Whisper «{self.name}» готов за {time.monotonic() - t0:.1f} с")
            if first:
                self.notify("Распознавание речи на Mac готово — отвечать буду быстрее.")
            self.ready.set()
        except Exception as e:
            self.failed = True
            print(f"[уши] Whisper не включился ({e}) — отправляю в Google запись, как раньше")

    @property
    def active(self) -> bool:
        return self.ready.is_set() and not self.failed

    def transcribe(self, wav: bytes, lang: str = "ru") -> str | None:
        """Текст фразы или None (тишина, шум, «галлюцинация», Whisper не готов)."""
        if not self.active:
            return None
        with wave.open(io.BytesIO(wav)) as w:
            rate = w.getframerate()
            a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if rate != 16000:
            idx = np.linspace(0, len(a) - 1, int(len(a) * 16000 / rate))
            a = np.interp(idx, np.arange(len(a)), a).astype(np.float32)
        t0 = time.monotonic()
        with self._lock:
            segs, info = self.model.transcribe(a, language=lang, beam_size=1, vad_filter=False,
                                               condition_on_previous_text=False, without_timestamps=True)
            segs = list(segs)
        self.last_secs = time.monotonic() - t0
        if not segs:
            return None
        if sum(s.no_speech_prob for s in segs) / len(segs) > 0.6:
            return None
        if sum(s.avg_logprob for s in segs) / len(segs) < -1.2:
            return None                                       # совсем не уверен — пусть Google слушает сам
        text = " ".join(s.text.strip() for s in segs).strip()
        low = text.lower()
        if not text or any(j in low for j in JUNK):
            return None
        return text
