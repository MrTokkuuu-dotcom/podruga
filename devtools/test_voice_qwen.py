"""Новый голос (Qwen3-TTS, свой голос девочки). Нужна модель в ~/Podruga/models/tts/.
Запуск: ~/Podruga/venv/bin/python devtools/test_voice_qwen.py"""
import statistics
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from voice_qwen import QwenVoiceOut, lang_name  # noqa: E402

assert lang_name("Привет, как дела?") == "russian" and lang_name("How are you?") == "english"
assert lang_name("오늘 뭐 해?") == "korean"

v = QwenVoiceOut(Path.home() / "Podruga", voice="anya")
assert v.ready.wait(300) and not v.failed, "голос не загрузился"
times = []
for text in ["Привет! Я так рада тебя видеть.", "How was your day?", "오늘 하루 어땠어?", "Ой, смотри, уже темно."]:
    t0 = time.monotonic()
    audio, rate = v.synth(text, "joy")
    dt = time.monotonic() - t0
    times.append(dt)
    dur = len(audio) / rate
    print(f"{text}: {dt:.2f} с на {dur:.1f} с речи")
    assert rate == 24000 and audio.dtype.name == "int16" and 0.5 < dur < 8, (rate, audio.dtype, dur)
    assert abs(int(audio.max())) > 1000, "тишина вместо голоса"

# по кусочкам: первый кусок быстро, сумма — вся фраза
firsts = []
for text in ["Ты сегодня так много работал, я тобой горжусь. Отдохни немножко, ладно?", "Oh, look, it's already dark outside."]:
    t0 = time.monotonic(); first = None; total = 0
    for a, r in v.synth_stream(text):
        first = first or time.monotonic() - t0
        total += len(a)
    firsts.append(first)
    print(f"по кусочкам: первый звук {first:.2f} с, всего {total / 24000:.1f} с речи за {time.monotonic() - t0:.1f} с")
    assert total / 24000 > 1.5
assert max(firsts) < 1.2, firsts

# две фразы из разных потоков — по очереди, без падения
out = {}
th = [threading.Thread(target=lambda k=k: out.setdefault(k, v.synth("Раз, два, три.")[0])) for k in range(2)]
[t.start() for t in th]; [t.join(60) for t in th]
assert len(out) == 2 and all(len(a) for a in out.values())

# другая девочка — другой голос, тот же объект
v.voice = "alisa"
a2, _ = v.synth("Привет! Я так рада тебя видеть.")
assert len(a2) > 0
print(f"медиана {statistics.median(times):.2f} с на фразу")
assert statistics.median(times) < 2.5
print("OK")
