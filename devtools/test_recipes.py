"""Рецепты «глаз и рук»: какие просьбы узнаются, какие ссылки, ожидание кнопки.
Запуск: ~/Podruga/venv/bin/python devtools/test_recipes.py"""
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recipes  # noqa: E402
from eyes import Element, Snapshot  # noqa: E402

bad = []
YTM = "https://music.youtube.com/search?q="
YT = "https://www.youtube.com/results?search_query="
for text, name, url in [
    ("включи кино группа крови в ютуб музыке", "ytmusic", YTM + quote("кино группа крови")),
    ("Аня, поставь Цоя на youtube music", "ytmusic", YTM + quote("цоя")),
    ("включи на ютуб музыке песню звезда по имени солнце", "ytmusic", YTM + quote("звезда по имени солнце")),
    ("유튜브 뮤직에서 아이유 틀어줘", "ytmusic", YTM + quote("아이유")),
    ("play blackpink on youtube music", "ytmusic", YTM + quote("blackpink")),
    ("найди на ютубе как варить рамен", "youtube", YT + quote("как варить рамен")),
    ("включи на youtube котиков", "youtube", YT + quote("котиков")),
    ("유튜브에서 고양이 영상 찾아줘", "youtube", YT + quote("고양이 영상")),
    ("найди наушники на купанге", "coupang", "https://www.coupang.com/np/search?q=" + quote("наушники")),
    ("найди в навере погоду в сеуле", "naver", "https://search.naver.com/search.naver?query=" + quote("погоду в сеуле")),
    ("загугли рецепт борща", "google", "https://www.google.com/search?q=" + quote("рецепт борща")),
]:
    r = recipes.find(text)
    if r is None or r.name != name or r.url != url:
        bad.append(f"{text!r} → {r and (r.name, r.url)}, ждал {(name, url)}")
for text in ["как дела", "я вчера смотрел ютуб", "включи музыку", "ютуб музыка лучше спотифая?", "найди", ""]:
    if recipes.find(text) is not None:
        bad.append(f"{text!r} не рецепт")
if recipes.find("найди наушники на купанге").target is not None:
    bad.append("на купанге только открыть, ничего не жать")


class Eyes:
    def __init__(self, appear_at):
        self.n, self.at = 0, appear_at

    def snapshot(self):
        self.n += 1
        els = [Element(1, "AXButton", "Поиск", (0, 0, 9, 9), ref="s")]
        if self.at and self.n >= self.at:
            els.append(Element(2, "AXButton", "Воспроизвести «Группа крови»", (0, 0, 9, 9), ref="p"))
            els.append(Element(3, "AXButton", "Play", (0, 0, 9, 9), ref="p2"))
        return Snapshot("Google Chrome", "com.google.Chrome", "YouTube Music", els, [], 1)


class Hands:
    def __init__(self):
        self.pressed = []

    def press(self, el, app, bid, confirmed=False):
        self.pressed.append(el.ref)
        return "нажала"


opened = []
r = recipes.find("включи кино группа крови в ютуб музыке")
t = [0.0]


def clock():
    return t[0]


def sleep(s):
    t[0] += s


h = Hands()
ok = recipes.run(r, Eyes(3), h, opened.append, timeout=8, sleep=sleep, clock=clock)
if not ok or h.pressed != ["p"] or opened != [r.url]:
    bad.append(f"кнопка на 3-м снимке: ok={ok} pressed={h.pressed} opened={opened}")
t[0] = 0.0
h = Hands()
ok = recipes.run(r, Eyes(None), h, opened.append, timeout=8, sleep=sleep, clock=clock)
if ok or h.pressed or t[0] < 8:
    bad.append(f"кнопка не появилась: ok={ok} pressed={h.pressed} t={t[0]}")
h = Hands()
ok = recipes.run(recipes.find("найди наушники на купанге"), Eyes(None), h, opened.append, sleep=sleep, clock=clock)
if not ok or h.pressed:
    bad.append("купанг: только открыть")

if bad:
    print("\n".join(bad))
    sys.exit(1)
print("OK")
