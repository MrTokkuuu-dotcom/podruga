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

# v40: «нажал — слушает, нажал ещё раз — закончил» и «держать»
import types  # noqa: E402
bs = types.ModuleType("bootstrap")
bs.__getattr__ = lambda n: (lambda *a, **k: None)
sys.modules["bootstrap"] = bs
import main  # noqa: E402


class _UI:
    def __getattr__(self, n):
        return lambda *a, **k: None


class _P:
    paused = False


c = main.Companion.__new__(main.Companion)
c.listener, c.ui, c.pauser, c.stt, c.speaking, c.awake = L, _UI(), _P(), None, False, True
c._park_later = lambda *a: None
L.held = False
c.cfg = {"microphone": {"ptt_style": "toggle"}}
c._ptt_event(True); c._ptt_event(False)
if not L.held:
    bad.append("toggle: после первого нажатия не слушает")
c._ptt_event(True); c._ptt_event(False)
if L.held:
    bad.append("toggle: второе нажатие не закончило")
c.cfg = {"microphone": {"ptt_style": "hold"}}
c._ptt_event(True)
h1 = L.held
c._ptt_event(False)
if not h1 or L.held:
    bad.append("hold: держать — слушает, отпустил — нет")
if main.Companion.__dict__.get("respond") and "filler" not in open(main.__file__, encoding="utf-8").read():
    bad.append("respond без filler?")
import yaml  # noqa: E402
cy = yaml.safe_load(open(Path(main.__file__).with_name("config.yaml"), encoding="utf-8"))
if cy["brain"].get("filler") is not False:
    bad.append("«Хм, сейчас подумаю» снова включено по умолчанию")

# v41: по журналу 29.11 (ITpedia, Маркарян, собаки, «давай по-английски»)
for goal, name, q in [("Так, найди пожалуйста на YouTube канал Арсена Маркаряна.", "youtube_channel", "арсена маркаряна"),
                      ("открыть канал ITpedia на YouTube и включить самое последнее видео", "youtube_latest", "itpedia"),
                      ("Зайди на канал Marmokka на ютубе и поставь его видео", "youtube_latest", "marmokka"),
                      ("search for the ITpedia channel on youtube", "youtube_channel", "itpedia")]:
    r = recipes.find(goal)
    if not r or (r.name, r.query) != (name, q) or "%25" in r.url:
        bad.append(f"ютуб: «{goal}» → {r and (r.name, r.query, r.url)}")
import intents  # noqa: E402
for t, want in [("Let's talk English now.", "РЕЖИМ english"), ("오케이 이제 한국어로 말을 하자.", "РЕЖИМ корейский"),
                ("Why you speak Russian?", None), ("я учу английский", None)]:
    if intents.device_command(t) != want:
        bad.append(f"язык: «{t}» → {intents.device_command(t)}")
if intents.body_command("Все, хватит ходить, хватит, хватит, присядь.") != "sit":
    bad.append("«…хватит, присядь» — не села")
for f in ["[разное] Обсуждает еду (готовить/не готовить).", "[о нём] Обсуждает с собеседницей, какой ролик поставить."]:
    if not memory.junk_fact(f):
        bad.append(f"память пропустила мусор: {f}")
import tempfile  # noqa: E402
import voice_qwen  # noqa: E402
pc = voice_qwen.PhraseCache(Path(tempfile.mkdtemp()))
pc.put("anya", "Вот, открыла.", np.ones(24000, np.int16))
if pc.get("anya", "вот,  открыла.") is None or pc.get("alisa", "Вот, открыла.") is not None:
    bad.append("готовые фразы: не нашла своё или нашла чужим голосом")
pc.put("anya", "Очень длинная фраза " * 10, np.ones(24000, np.int16))
if pc.get("anya", "Очень длинная фраза " * 10) is not None:
    bad.append("готовые фразы: длинные хранить не надо")
import agent  # noqa: E402
if not agent.build_prompt("цель", [], "экран").startswith(agent.RULES):
    bad.append("агент: правила не в начале — кэш не сработает")

if bad:
    print("FAIL\n" + "\n".join(bad))
    sys.exit(1)
print("OK: кнопка, YouTube (каналы, свежее), язык, память, готовые фразы, кэш агента")
