"""Корейский голос — встроенный голос Mac (Yuna и другие из «Системных настроек → Универсальный доступ →
Устный контент»). Бесплатно, без интернета, работает на компьютере пользователя: голос — часть macOS.
Говорит прямо внутри программы (без запуска `say`): ~0,05 с на фразу после разогрева.
Если поставить в macOS «улучшенную» или «премиум» версию корейского голоса — возьмёт её сама."""
import struct
import tempfile
import threading
import time
from pathlib import Path

import numpy as np


def _ext80(b: bytes) -> float:
    """80-битное число (частота в AIFF)."""
    exp, mant = struct.unpack(">HQ", b)
    return mant * 2.0 ** ((exp & 0x7FFF) - 16383 - 63)


def read_aiff(data: bytes) -> tuple[np.ndarray, int]:
    """AIFF / AIFF-C (16 бит, NONE/twos — big-endian, sowt — little-endian) → (int16 моно, частота)."""
    pos, rate, ch, comp, pcm = 12, 22050, 1, b"NONE", b""
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"COMM":
            ch = struct.unpack(">h", body[0:2])[0]
            rate = int(_ext80(body[8:18]))
            if len(body) >= 22:
                comp = body[18:22]
        elif cid == b"SSND":
            off = struct.unpack(">I", body[0:4])[0]
            pcm = body[8 + off:]
        pos += 8 + size + (size & 1)
    a = np.frombuffer(pcm[:len(pcm) // 2 * 2], dtype="<i2" if comp == b"sowt" else ">i2").astype(np.int16)
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1).astype(np.int16)
    return a, rate


def _best_voice(lang_prefix: str = "ko") -> str | None:
    from AppKit import NSSpeechSynthesizer
    voices = [str(v) for v in NSSpeechSynthesizer.availableVoices()]
    mine = [v for v in voices if f".{lang_prefix}-" in v.lower() or f".{lang_prefix}_" in v.lower()]
    if not mine:
        return None
    rank = lambda v: (0 if "premium" in v else 1 if "enhanced" in v else 2, 0 if "yuna" in v.lower() else 1)
    return sorted(mine, key=rank)[0]


class KoreanVoiceOut:
    def __init__(self):
        self.voice = _best_voice("ko")
        if not self.voice:
            raise RuntimeError("в macOS нет корейского голоса")
        self.rate = 22050
        self._lock = threading.Lock()
        self._sp = None
        self._dir = Path(tempfile.mkdtemp(prefix="podruga_ko_"))
        print(f"[голос] корейский: {self.voice.split('.')[-1]} ({'улучшенный' if 'compact' not in self.voice else 'обычный'})")

    def synth(self, text: str) -> np.ndarray:
        from AppKit import NSSpeechSynthesizer
        from Foundation import NSURL, NSRunLoop, NSDate
        with self._lock:
            if self._sp is None:
                self._sp = NSSpeechSynthesizer.alloc().initWithVoice_(self.voice)
            path = self._dir / "phrase.aiff"
            path.unlink(missing_ok=True)
            t0 = time.monotonic()
            self._sp.startSpeakingString_toURL_(text, NSURL.fileURLWithPath_(str(path)))
            deadline = t0 + 15
            while self._sp.isSpeaking() and time.monotonic() < deadline:
                NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.01))
            if not path.exists():
                return np.zeros(0, dtype=np.int16)
            a, self.rate = read_aiff(path.read_bytes())
            print(f"[голос] корейский: {time.monotonic() - t0:.2f} с на {len(a) / self.rate:.1f} с речи")
            return a
