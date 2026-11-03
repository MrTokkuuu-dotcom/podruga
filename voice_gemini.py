"""Живой голос: Gemini TTS. Звучит как настоящая девушка, понимает указания по манере
(«мило, тепло, игриво»). Если облако недоступно — автоматически старый голос Piper."""
import base64
import io
import os
import time
import wave

import numpy as np

RATE = 24000


def _get(obj, name):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _decode_audio(data) -> tuple[np.ndarray, int]:
    raw = base64.b64decode(data) if isinstance(data, str) else bytes(data)
    rate = RATE
    if raw[:4] == b"RIFF":
        with wave.open(io.BytesIO(raw)) as w:
            rate = w.getframerate()   # берём частоту из файла, а не угадываем
            raw = w.readframes(w.getnframes())
    if len(raw) % 2:
        raw = raw[:-1]  # обрезок байта превращался в шум
    return np.frombuffer(raw, dtype=np.int16).copy(), rate


COOLDOWN_S = 10 * 60      # после «лимит исчерпан» 10 минут говорим запасным голосом
HARD_LIMIT_S = 25         # дольше этого не ждём облако ни при каких условиях


class GeminiVoiceOut:
    def __init__(self, model: str, voice: str, style: str, fallback=None):
        from concurrent.futures import ThreadPoolExecutor

        from google import genai
        from google.genai import types
        # Без повторов: библиотека Google сама повторяла упавший запрос с паузами,
        # и она «думала» минутами. Теперь одна попытка, а дальше — запасной голос.
        self.client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY"),
            http_options=types.HttpOptions(timeout=20_000,
                                           retry_options=types.HttpRetryOptions(attempts=1)))
        self.model, self.voice_name, self.style = model, voice, style
        self.fallback = fallback      # PiperVoiceOut или None
        self.rate = RATE
        self.cloud_off_until = 0.0
        self.notify = print           # окно подставит сюда показ сообщения в переписке
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tts")

    def _request(self, text: str) -> tuple[np.ndarray, int]:
        content = {"type": "text", "text": text}
        if self.style:
            content["annotations"] = [{"type": "speech_metadata", "style": self.style}]
        result = self.client.interactions.create(
            model=self.model,
            input=[{"type": "user_input", "content": [content]}],
            response_format={"type": "audio"},
            generation_config={"speech_config": [{"voice": self.voice_name}]},
            timeout=20,
        )
        audio = _get(result, "output_audio")
        data = _get(audio, "data")
        if not data:
            raise RuntimeError("Gemini не вернул звук")
        return _decode_audio(data)

    def _cloud(self, text: str) -> tuple[np.ndarray, int]:
        """Запрос в облако с жёстким ограничением по часам."""
        future = self._pool.submit(self._request, text)
        return future.result(timeout=HARD_LIMIT_S)

    def synth(self, text: str) -> tuple[np.ndarray, int]:
        """Возвращает (звук, частота). Частота разная у Gemini и Piper."""
        if time.monotonic() >= self.cloud_off_until:
            try:
                t0 = time.monotonic()
                audio, rate = self._cloud(text)
                print(f"[голос] озвучено за {time.monotonic() - t0:.1f} с: {len(audio) / rate:.1f} с речи")
                return audio, rate
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                print(f"[голос] облачный голос не ответил: {msg[:300]}")
                quota = any(k in msg for k in ("429", "RESOURCE_EXHAUSTED", "quota", "Quota"))
                self.cloud_off_until = time.monotonic() + (COOLDOWN_S if quota else 60)
                if quota:
                    self.notify("Бесплатный лимит облачного голоса на сейчас закончился — "
                                "пока говорю запасным голосом.")
        if self.fallback:
            return self.fallback.synth(text), self.fallback.rate
        return np.zeros(0, dtype=np.int16), RATE
