"""Голос Silero: бесплатно, прямо на Mac, без интернета и без лимитов.
Модель v5 (2025) сама ставит ударения и понимает вопросы/восклицания.
Женские голоса: xenia, kseniya, baya. Тон и темп — через SSML.
Лицензия моделей Silero — только некоммерческая (для себя можно, для продажи нельзя)."""
import threading
import time
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np

MODELS = ["v5_6_ru", "v5_5_ru", "v5_ru"]          # от новой к старой
URL = "https://models.silero.ai/models/tts/ru/{}.pt"
RATE = 24000
SPEAKERS = [("xenia", "Ксения — мягкая, молодая"), ("kseniya", "Ксюша — звонкая"),
            ("baya", "Бая — спокойная")]
PITCH = {"обычный": "medium", "повыше": "high", "высокий": "x-high"}
PITCH_LADDER = ["x-low", "low", "medium", "high", "x-high"]
RATE_LADDER = ["x-slow", "slow", "medium", "fast", "x-fast"]
# эмоция → (сдвиг тона, сдвиг темпа) относительно выбранного в настройках
EMOTION_PROSODY = {
    "joy": (+1, +1), "surprise": (+1, 0), "shy": (+1, -1), "tender": (0, -1),
    "sad": (-1, -1), "think": (0, -1), "calm": (0, 0),
}


def _shift(ladder: list[str], base: str, step: int) -> str:
    i = ladder.index(base) if base in ladder else 2
    return ladder[max(0, min(len(ladder) - 1, i + step))]


def _download(dest: Path, notify) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for mid in MODELS:
        f = dest / f"silero_{mid}.pt"
        if f.exists() and f.stat().st_size > 1_000_000:
            return f
    for mid in MODELS:
        f = dest / f"silero_{mid}.pt"
        part = f.with_suffix(".part")
        try:
            notify("Скачиваю новый голос (один раз, пару минут)…")
            t0 = time.monotonic()
            urllib.request.urlretrieve(URL.format(mid), part)
            part.rename(f)
            print(f"[голос] модель {mid} скачана за {time.monotonic() - t0:.0f} с")
            return f
        except Exception as e:
            print(f"[голос] не скачалась {mid}: {e}")
            part.unlink(missing_ok=True)
    raise RuntimeError("не получилось скачать модель Silero")


class SileroVoiceOut:
    """Загружается в фоне. Пока грузится — говорит запасной голос (fallback)."""

    def __init__(self, models_dir: Path, speaker: str = "xenia", pitch: str = "medium",
                 speed: str = "medium", fallback=None, notify=print):
        self.speaker, self.pitch, self.speed = speaker, pitch, speed
        self.fallback = fallback
        self.notify = notify
        self.rate = RATE
        self.model = None
        self._lock = threading.Lock()
        self.ready = threading.Event()
        threading.Thread(target=self._load, args=(Path(models_dir),), daemon=True).start()

    def _load(self, models_dir: Path):
        try:
            import torch
            torch.set_num_threads(4)
            path = _download(models_dir, self.notify)
            t0 = time.monotonic()
            model = torch.package.PackageImporter(str(path)).load_pickle("tts_models", "model")
            model.to(torch.device("cpu"))
            self.model = model
            self.ready.set()
            print(f"[голос] Silero {path.stem} готов за {time.monotonic() - t0:.1f} с")
            self.synth("Привет.")     # прогрев: первая фраза потом звучит без задержки
        except Exception as e:
            print(f"[голос] Silero не загрузился: {e}")
            self.notify("Новый голос не загрузился — говорю запасным.")

    def _ssml(self, text: str, emotion: str = "calm") -> str | None:
        dp, dr = EMOTION_PROSODY.get(emotion, (0, 0))
        pitch = _shift(PITCH_LADDER, self.pitch, dp)
        rate = _shift(RATE_LADDER, self.speed, dr)
        if pitch == "medium" and rate == "medium":
            return None
        return (f'<speak><prosody pitch="{pitch}" rate="{rate}">'
                f"{escape(text)}</prosody></speak>")

    def synth(self, text: str, emotion: str = "calm") -> tuple[np.ndarray, int]:
        if self.model is None:
            if self.fallback:
                return self.fallback.synth(text), self.fallback.rate
            return np.zeros(0, dtype=np.int16), RATE
        t0 = time.monotonic()
        with self._lock:
            ssml = self._ssml(text, emotion)
            try:
                if ssml:
                    audio = self.model.apply_tts(ssml_text=ssml, speaker=self.speaker, sample_rate=RATE)
                else:
                    audio = self.model.apply_tts(text=text, speaker=self.speaker, sample_rate=RATE)
            except Exception as e:
                print(f"[голос] Silero ошибка: {e}")
                if self.fallback:
                    return self.fallback.synth(text), self.fallback.rate
                return np.zeros(0, dtype=np.int16), RATE
        a = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
        a = np.clip(a * 32767, -32768, 32767).astype(np.int16)
        print(f"[голос] Silero: {time.monotonic() - t0:.2f} с на {len(a) / RATE:.1f} с речи")
        return a, RATE
