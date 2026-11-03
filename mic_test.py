"""Проверка микрофона: громкость и «насколько это голос» (фильтр Silero).
Помолчи, включи музыку, потом поговори — увидишь, как фильтр отличает голос."""
import time

import sounddevice as sd

from audio_in import RATE, SileroVAD, level

vad = SileroVAD()
F = vad.FRAME
print("Помолчи, включи музыку, потом поговори. Выход — Ctrl+C.\n")
print("громкость | голос?")
with sd.RawInputStream(samplerate=RATE, blocksize=F, dtype="int16", channels=1) as s:
    peak, best, t0 = 0.0, 0.0, time.time()
    while True:
        data, _ = s.read(F)
        frame = bytes(data)
        peak = max(peak, level(frame))
        best = max(best, vad.prob(frame))
        if time.time() - t0 >= 0.5:
            mark = "ГОЛОС" if best >= 0.6 else "     "
            print(f"{peak:7.0f}   | {best:4.2f} {mark} " + "█" * min(int(peak / 50), 40))
            peak, best, t0 = 0.0, 0.0, time.time()
