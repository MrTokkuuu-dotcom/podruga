"""Голосовые команды, которые распознаются прямо на компьютере (Vosk, ~45 МБ, без интернета):
«привет, подруга» — будит, «спокойной ночи» — усыпляет, «посмотри / глянь» — смотрит на экран.
Пока она спит, ничего не уходит в облако."""
import io
import json
import wave
from dataclasses import dataclass

RATE = 16000  # как в audio_in

LOOK_PHRASES = ["посмотри", "глянь", "смотри", "что на экране", "на экран", "на экране"]


def _norm(text: str) -> str:
    for ch in ",.!?":
        text = text.replace(ch, " ")
    return " ".join(text.lower().replace("ё", "е").split())


@dataclass
class Heard:
    kind: str | None = None       # 'wake' | 'sleep' | None
    has_request: bool = False     # кроме команды в фразе есть ещё что-то
    look: bool = False            # просит посмотреть на экран


class WakeWord:
    def __init__(self, model_dir: str, wake_phrases: list[str], sleep_phrases: list[str],
                 look_phrases: list[str] | None = None):
        from vosk import KaldiRecognizer, Model, SetLogLevel
        SetLogLevel(-1)
        self._Rec = KaldiRecognizer
        self.model = Model(model_dir)
        self.wake = [_norm(p) for p in wake_phrases]
        self.sleep = [_norm(p) for p in sleep_phrases]
        self.look = [_norm(p) for p in (look_phrases or LOOK_PHRASES)]
        # Ограниченный словарь: только наши слова + «[unk]» для всего остального.
        # Так маленькая модель почти не путает команду с обычной речью.
        phrases = self.wake + self.sleep + self.look
        words = sorted({w for p in phrases for w in p.split()})
        self.grammar = json.dumps(phrases + words + ["[unk]"], ensure_ascii=False)

    def hear(self, wav: bytes) -> str:
        with wave.open(io.BytesIO(wav)) as w:
            pcm = w.readframes(w.getnframes())
        rec = self._Rec(self.model, RATE, self.grammar)
        rec.AcceptWaveform(pcm)
        return _norm(json.loads(rec.FinalResult()).get("text", ""))

    def check(self, wav: bytes) -> Heard:
        return classify(self.hear(wav), self.wake, self.sleep, self.look)


def classify(heard: str, wake: list[str], sleep: list[str],
             look: list[str] | None = None) -> Heard:
    heard = _norm(heard)
    look_hit = any(_norm(p) in heard for p in (look or []))
    for kind, phrases in (("sleep", sleep), ("wake", wake)):
        for p in phrases:
            p = _norm(p)
            if p in heard:
                rest = heard.replace(p, " ", 1).replace("[unk]", " x ").split()
                return Heard(kind, len(rest) >= 1, look_hit)
    return Heard(None, False, look_hit)


def is_goodbye(transcript: str, phrases: list[str]) -> bool:
    t = _norm(transcript)
    return any(_norm(p) in t for p in phrases)
