"""Голос по кусочкам: Speaker начинает играть первый кусок, не дожидаясь всей фразы. Без звуковой карты.
Запуск: ~/Podruga/venv/bin/python devtools/test_speaker_stream.py"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tts  # noqa: E402

played: list[tuple[float, int]] = []


class FakeStream:
    def write(self, a): played.append((time.monotonic(), len(a)))
    def close(self): pass


tts.Speaker._open_stream = lambda self: FakeStream()


class SlowStreamVoice:
    rate = 24000

    def synth(self, text, emotion="calm"):
        raise AssertionError("при потоковом голосе synth() целиком не нужен")

    def synth_stream(self, text, emotion="calm"):
        for _ in range(3):                      # три куска по 0,5 с, каждый готовится 0,3 с
            time.sleep(0.3)
            yield np.full(12000, 8000, dtype=np.int16), 24000


sp = tts.Speaker(SlowStreamVoice())
t0 = time.monotonic()
sp.speak("Привет! Как дела?")
sp.wait_done()
first = played[0][0] - t0
total = sum(n for _, n in played)
print(f"первый звук через {first:.2f} с, всего {total / 24000:.2f} с звука")
assert first < 0.5, "первый кусок должен заиграть сразу, а не после всей фразы (0,9 с)"
assert 1.5 <= total / 24000 <= 1.7, total      # 3 × 0,5 с + пауза после фразы, без лишних пауз между кусками

# старый голос без synth_stream — как раньше
class OldVoice:
    rate = 24000
    def synth(self, text, emotion="calm"): return np.full(24000, 8000, dtype=np.int16), 24000


played.clear()
sp2 = tts.Speaker(OldVoice()); sp2.speak("Раз."); sp2.wait_done()
assert sum(n for _, n in played) >= 24000
print("OK")
