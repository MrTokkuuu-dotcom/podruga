"""Распознавание речи прямо на Mac. В Google уходит уже текст, а не запись:
запрос легче и быстрее, лимит тратится меньше, а готовые ответы срабатывают чаще.

Основной слух (v27) — Whisper large-v3-turbo на видеочипе Mac (MLX): русский, английский и корейский,
сам понимает язык каждой фразы, английские названия пишет как есть (Valorant, Discord). ~0,3 с на фразу:
модели даётся только длина фразы + 6 с тишины, а не все 30 с (без запаса она «заедает» и повторяет).
Модель ~1,6 ГБ скачивается один раз в ~/Podruga/models/whisper-mlx; библиотека mlx-whisper ставится
фоном сама. Пока их нет или что-то не встало — работает прежний Whisper «small» (faster-whisper).
Если и его нет — она по-старому отправляет в Google саму запись."""
import io
import math
import os
import re
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

# Известные «галлюцинации» Whisper на тишине и шуме (особенно по-русски)
JUNK = ("субтитры", "продолжение следует", "редактор субтитров", "dimatorzok", "спасибо за просмотр",
        "подписывайтесь", "ставьте лайки", "amara.org", "сделано с любовью", "корректор",
        "благодарю за внимание", "до новых встреч", "всем пока", "music", "музыка",
        "thanks for watching", "thank you for watching", "subscribe", "subtitles by",
        "시청해주셔서", "구독과 좋아요", "자막", "mbc 뉴스", "kbs 뉴스")
# Целиком «выдуманные» фразы на тишине (только если это ВСЯ фраза)
JUNK_WHOLE = {"thank you", "thank you.", "thanks.", "you", "bye.", "bye", "감사합니다.", "감사합니다", "아."}


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
        logp = sum(s.avg_logprob for s in segs) / len(segs)
        if logp < -1.2:
            return None                                       # совсем не уверен — пусть Google слушает сам
        if max(s.compression_ratio for s in segs) > 2.4:
            return None                                       # «бла-бла-бла» по кругу — выдумал из шума
        text = " ".join(s.text.strip() for s in segs).strip()
        low = text.lower()
        letters = sum(ch.isalpha() for ch in text)
        if not text or letters < 2 or any(j in low for j in JUNK):
            return None
        if len(low.split()) == 1 and logp < -0.6:
            return None                                       # одно неуверенное слово из шума («Говорит»)
        return text


# ---------- основной слух: Whisper large-v3-turbo на видеочипе (MLX) ----------
MLX_PKGS = ["mlx==0.32.4", "mlx-whisper==0.4.3"]
MLX_REPO = "mlx-community/whisper-large-v3-turbo"
# Частые английские названия — подсказка модели: пишет их латиницей, а не «Валорант»
BASE_HINTS = ["Valorant", "Discord", "YouTube", "Steam", "Minecraft", "Genshin Impact", "Telegram", "Spotify",
              "KakaoTalk", "Netflix", "TikTok", "Instagram", "ChatGPT", "Claude", "Google", "CapCut",
              "League of Legends", "Counter-Strike", "Dota", "Roblox", "Fortnite", "PUBG", "Overwatch"]


# Корейская подсказка: обычный разговор + еда, места, игры хангылем — чтобы писал «떡볶이», а не «tteok»
KO_PROMPT = ("친구랑 편하게 반말로 수다 떠는 중이야. 떡볶이, 순대, 김밥, 라면, 김치찌개, 된장찌개, 순두부찌개, "
             "부대찌개, 두루치기, 제육볶음, 닭갈비, 닭볶음탕, 삼겹살, 소주, 치킨, 짜장면, 짬뽕, 탕수육, 냉면, 갈비, "
             "불고기, 비빔밥, 국밥, 떡국, 족발, 보쌈, 마라탕, 탕후루, 편의점, 배달, 피시방, 카톡, 유튜브, 발로란트.")


def _repeat_cut(text: str) -> str:
    """Убрать повтор одной и той же фразы подряд («Привет. Привет. Привет.»)."""
    parts = re.split(r"(?<=[.!?。？！])\s+", text.strip())
    out = []
    for p in parts:
        if out and p.strip().lower() == out[-1].strip().lower():
            continue
        out.append(p)
    if len(out) > 1 and out[-1].strip().lower() != out[-2].strip().lower() and \
            out[-2].strip().lower().startswith(out[-1].strip(" .�").lower()):
        out.pop()                                           # оборванный повтор в конце («…가자. 냉»)
    return " ".join(out).replace("�", "")


class _NoSTT:
    """Заглушка вместо прежнего слуха, когда он не нужен."""
    active = False
    last_secs = 0.0
    model = None

    def transcribe(self, wav, lang="ru"):
        return None


class MlxWhisperSTT:
    """Тот же разговор, что у WhisperSTT: active, transcribe(wav, lang) → текст или None, last_secs.
    Плюс last_lang — на каком языке была фраза (ru / en / ko)."""

    def __init__(self, home: Path, repo: str = MLX_REPO, languages=("ru", "en", "ko"), fallback_model="small",
                 notify=print, hints=None):
        self.home = Path(home)
        self.repo = repo
        self.dir = self.home / "models" / "whisper-mlx" / repo.split("/")[-1]
        self.languages = tuple(languages)
        self.notify = notify
        self.hints = hints or (lambda: [])
        self.model = None
        self.failed = False
        self.ready = threading.Event()
        self.last_secs = 0.0
        self.last_lang = "ru"
        self._lock = threading.Lock()
        self.fallback_model = fallback_model
        import importlib.util
        have = importlib.util.find_spec("mlx_whisper") is not None and (self.dir / "weights.safetensors").exists()
        # прежний слух нужен, только пока новый ставится и скачивается (или если новый не встал)
        self.fallback = _NoSTT() if have else WhisperSTT(home, fallback_model, notify=lambda m: None)
        threading.Thread(target=self._load, name="whisper-mlx-load", daemon=True).start()

    # --- установка и загрузка ---
    def _install(self) -> bool:
        uv = self.home / "bin" / "uv"
        if os.environ.get("PODRUGA_BUNDLED") or not uv.exists():
            return False
        stamp = self.home / ".mlx_whisper_failed"
        if stamp.exists() and stamp.read_text().strip() == " ".join(MLX_PKGS):
            return False                                   # уже пробовали эти версии — не вышло, не мучаем
        print("[уши] ставлю новый слух (mlx-whisper)…", flush=True)
        r = subprocess.run([str(uv), "pip", "install", "--python", sys.executable, "-q", *MLX_PKGS],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[уши] новый слух не встал — остаюсь на прежнем:\n{r.stderr[-800:]}", flush=True)
            stamp.write_text(" ".join(MLX_PKGS))
            return False
        return True

    def _load(self):
        try:
            import importlib
            try:
                importlib.import_module("mlx_whisper")         # библиотека уже стоит?
            except ImportError:
                if not self._install():
                    raise RuntimeError("mlx-whisper недоступен")
                importlib.invalidate_caches()
                importlib.import_module("mlx_whisper")
            import mlx.core as mx
            from mlx_whisper.load_models import load_model
            if not (self.dir / "weights.safetensors").exists() and not any(self.dir.glob("*.npz")):
                self.notify("Ставлю новый слух: русский, английский и корейский (~1,6 ГБ, один раз). "
                            "Пока слушаю по-старому.")
                from huggingface_hub import snapshot_download
                self.dir.mkdir(parents=True, exist_ok=True)
                snapshot_download(self.repo, local_dir=str(self.dir))
                first = True
            else:
                first = False
            t0 = time.monotonic()
            self.model = load_model(str(self.dir), dtype=mx.float16)
            self._mx = mx
            self._transcribe_array(np.zeros(16000, dtype=np.float32))      # прогрев
            print(f"[уши] Whisper large-v3-turbo (видеочип) готов за {time.monotonic() - t0:.1f} с")
            if first:
                self.notify("Новый слух готов: понимаю русский, английский и корейский.")
            self.ready.set()
            self.fallback.model = None                      # прежний больше не нужен — освобождаем память
        except Exception as e:
            self.failed = True
            print(f"[уши] Whisper large-v3-turbo не включился ({e}) — слушаю прежним Whisper")
            if isinstance(self.fallback, _NoSTT):
                self.fallback = WhisperSTT(self.home, self.fallback_model, notify=lambda m: None)

    @property
    def active(self) -> bool:
        return (self.ready.is_set() and not self.failed) or self.fallback.active

    # --- распознавание ---
    def _prompt(self, lang: str = "ru") -> str:
        """Подсказка декодеру — на языке самой фразы: русская подсказка на корейской речи сбивает его на кириллицу."""
        names, seen = [], set()
        for n in list(self.hints()) + BASE_HINTS:
            n = str(n).strip()
            if n and n.lower() not in seen and len(n) < 40:
                seen.add(n.lower())
                names.append(n)
        if lang == "ko":
            return KO_PROMPT + " " + ", ".join(names[:14]) + "."
        if lang == "en":
            return "Chatting with a friend about games, food and life: " + ", ".join(names[:30]) + "."
        return "Названия пишем как есть: " + ", ".join(names[:30]) + "."

    def _transcribe_array(self, a: np.ndarray):
        import gpu
        gpu.mark_own()                                  # слух тоже на видеочипе — это мы, а не «тяжёлая программа»
        import mlx.nn as nn
        from mlx_whisper import audio, decoding
        mx, m = self._mx, self.model
        sec = len(a) / 16000
        mel = audio.log_mel_spectrogram(a, n_mels=m.dims.n_mels, padding=audio.N_SAMPLES)
        mel = audio.pad_or_trim(mel, audio.N_FRAMES, axis=-2).astype(mx.float16)
        ctx = min(m.dims.n_audio_ctx, int(math.ceil(sec + 6)) * 50)      # фраза + 6 с тишины, а не все 30 с
        e = m.encoder
        x = nn.gelu(e.conv1(mel[None]))
        x = nn.gelu(e.conv2(x))
        x = x[:, :ctx] + e._positional_embedding[:ctx]
        for b in e.blocks:
            x, _, _ = b(x)
        feats = e.ln_post(x)
        full = m.dims.n_audio_ctx
        m.dims.n_audio_ctx = ctx                            # декодеру — короткое окно
        try:
            _, probs = decoding.detect_language(m, feats)
            probs = probs[0] if isinstance(probs, list) else probs
            lang = max(self.languages, key=lambda k: probs.get(k, 0.0))   # только наши языки
            prev = self.last_lang
            if lang != prev and prev in self.languages and probs.get(prev, 0) > 0.2 \
                    and probs.get(lang, 0) < 0.6:
                lang = prev                                 # сомнение — остаёмся на языке разговора
            if probs.get(lang, 0) < 0.7:                   # язык неясен — пробуем каждый, берём самый уверенный
                cands = [self._fix(self._decode(feats, k, sec, prompt=True), k, feats, sec) for k in self.languages]
                bonus = lambda i: 0.3 if self.languages[i] == prev else 0.0
                i = max(range(len(cands)), key=lambda i: cands[i].avg_logprob + bonus(i))
                r, lang = cands[i], self.languages[i]
            else:
                r = self._fix(self._decode(feats, lang, sec, prompt=True), lang, feats, sec)
        finally:
            m.dims.n_audio_ctx = full
        return r, lang

    def _fix(self, r, lang, feats, sec):
        """Подсказка сбила на чужие буквы или вышло неуверенно — ещё раз без подсказки."""
        bad_script = (lang in ("ko", "en") and re.search(r"[А-Яа-яЁё]", r.text)) or \
                     (lang in ("ru", "en") and re.search(r"[가-힣]", r.text))
        if bad_script or r.avg_logprob < -0.8:
            r2 = self._decode(feats, lang, sec, prompt=False)
            if r2.compression_ratio <= 2.4 and (r2.avg_logprob > r.avg_logprob or bad_script):
                return r2
        return r

    def _decode(self, feats, lang: str, sec: float, prompt: bool):
        from mlx_whisper import decoding
        opts = decoding.DecodingOptions(language=lang, without_timestamps=True, fp16=True,
                                        prompt=self._prompt(lang) if prompt else None,
                                        sample_len=int(12 * sec + 16))
        r = decoding.decode(self.model, feats, opts)
        return r[0] if isinstance(r, list) else r

    def transcribe(self, wav: bytes, lang: str = "ru") -> str | None:
        if not (self.ready.is_set() and not self.failed):
            text = self.fallback.transcribe(wav, lang)
            self.last_secs, self.last_lang = self.fallback.last_secs, lang
            return text
        with wave.open(io.BytesIO(wav)) as w:
            rate = w.getframerate()
            a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if rate != 16000:
            idx = np.linspace(0, len(a) - 1, int(len(a) * 16000 / rate))
            a = np.interp(idx, np.arange(len(a)), a).astype(np.float32)
        if len(a) > 16000 * 25:
            a = a[-16000 * 25:]                             # очень длинная фраза — хвост (окно модели 30 с)
        if float(np.sqrt(np.mean(a * a))) < 0.002:
            self.last_secs = 0.0
            return None                                     # почти тишина — не гоняем модель зря
        t0 = time.monotonic()
        with self._lock:
            r, lang = self._transcribe_array(a)
        self.last_secs, self.last_lang = time.monotonic() - t0, lang
        text = _repeat_cut(r.text)
        looped = r.compression_ratio > 2.4 and len(text) < len(r.text.strip()) * 0.6   # зациклился на своей же фразе
        if r.no_speech_prob > 0.6 or r.avg_logprob < -1.0 or (r.compression_ratio > 2.4 and not looped):
            return None                                     # тишина, шум или «выдумал»
        low = text.lower()
        letters = sum(ch.isalpha() for ch in text)
        if not text or letters < 2 or any(j in low for j in JUNK) or low.strip() in JUNK_WHOLE and r.no_speech_prob > 0.2:
            return None
        if len(low) > 12 and low.strip(" .")[:20] in self._prompt(lang).lower():
            return None                                     # повторил подсказку вместо речи
        if len(low.split()) == 1 and r.avg_logprob < -0.6:
            return None
        return text


def make_stt(home: Path, st: dict, notify=print, hints=None):
    """По настройкам: engine "mlx" (по умолчанию, большой слух на видеочипе) или "small" (прежний)."""
    if st.get("engine", "mlx") == "mlx":
        return MlxWhisperSTT(home, st.get("mlx_model", MLX_REPO), st.get("languages", ["ru", "en", "ko"]),
                             st.get("model", "small"), notify=notify, hints=hints)
    return WhisperSTT(home, st.get("model", "small"), notify=notify)
