"""«Нажми и говори» (v37): слышит только пока зажата клавиша, отпустил — одна фраза; без клавиши — тишина,
даже если вокруг громко. Плюс выученные чинки v37: запрос YouTube без «я говорю …», мусор в памяти.
Запуск: ~/Podruga/venv/bin/python devtools/test_ptt.py"""
import queue
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np  # noqa: E402
from audio_in import Listener  # noqa: E402

bad = []
L = Listener()
L.ptt = True
threading.Thread(target=L._worker, daemon=True).start()
loud = (np.sin(np.arange(L.frame) / 3) * 8000).astype(np.int16).tobytes()


def feed(n):
    for _ in range(n):
        L._callback(np.frombuffer(loud, np.int16).reshape(-1, 1), L.frame, None, None)
        time.sleep(0.002)


feed(150)                                   # громко, но клавиша не зажата — фразы нет
time.sleep(0.4)
if not L.phrase_q.empty():
    bad.append("без клавиши услышала фразу")
L.muted = True                              # она говорит — а он зажал клавишу: всё равно слышит
L.press()
feed(60)                                    # ~1,9 с
L.release()
L.muted = False
try:
    wav, _ = L.phrase_q.get(timeout=2)
    secs = (len(wav) - 44) / 2 / 16000
    if not 1.6 < secs < 2.6:
        bad.append(f"длина фразы {secs:.2f} с")
except queue.Empty:
    bad.append("отпустил клавишу — фразы нет")
L.press(); feed(5); L.release()             # случайный тык (0,16 с) — не фраза
time.sleep(0.4)
if not L.phrase_q.empty():
    bad.append("короткий тык стал фразой")

import recipes  # noqa: E402
for goal, q in [("Я говорю поставь мне видео Шевцова на YouTube, любое.", "шевцова"),
                ("найти и включить видео Шевцова на YouTube", "шевцова"),
                ("открой YouTube и найди канал Ilia Shevцов", "ilia shevцов"),
                ("включи Hate Me в ютуб музыке", "hate me")]:
    r = recipes.find(goal)
    if not r or r.query != q:
        bad.append(f"запрос «{goal}» → {r and r.query!r}, ждала {q!r}")
import memory  # noqa: E402
for f, junk in [("[о нём] Просит найти факты о кошках на английском.", True),
                ("[о нём] Считает, что у него всё нормально с интернетом.", True),
                ("[любит] Любит аниме «Человек-бензопила»", False), ("[о нём] Учится в Пусане", False)]:
    if memory.junk_fact(f) != junk:
        bad.append(f"память: «{f}» мусор={not junk}")

if bad:
    print("FAIL\n" + "\n".join(bad))
    sys.exit(1)
print("OK: нажми и говори, запрос YouTube, память")
