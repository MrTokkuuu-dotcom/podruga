"""Рецепты «глаз и рук»: какие просьбы узнаются, какие ссылки, ожидание кнопки.
Запуск: ~/Podruga/venv/bin/python devtools/test_recipes.py"""
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import eyes  # noqa: E402
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
    ("включи песню Hate Me в YouTube Music", "ytmusic", YTM + quote("hate me")),
    ("play In the End on youtube music", "ytmusic", YTM + quote("in the end")),
    ("открой на этот мьюзик песню егора крида будильник", "ytmusic", YTM + quote("егора крида будильник")),
    ("Включи какое-нибудь видео на ютубе про кемпинг", "youtube", YT + quote("кемпинг")),
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
    """Страница YouTube Music: кнопки появляются на снимке appear_at; играет ли — общий флаг state."""

    def __init__(self, appear_at, state=None, labels=("Воспроизвести «Группа крови»", "Play")):
        self.n, self.at, self.state, self.labels = 0, appear_at, state or {"playing": False}, labels

    def snapshot(self):
        self.n += 1
        els = [Element(1, "AXButton", "Поиск", (0, 0, 9, 9), ref="s")]
        if self.at and self.n >= self.at:
            for i, lab in enumerate(self.labels):
                els.append(Element(2 + i, "AXButton", lab, (0, 0, 9, 9), ref=f"p{i}"))
        els.append(Element(9, "AXButton", "Пауза" if self.state["playing"] else "Воспроизвести", (0, 900, 9, 9),
                           ref="bar"))
        return Snapshot("Google Chrome", "com.google.Chrome", "YouTube Music", els, [], 1)

    is_playing = staticmethod(eyes.is_playing)


class Hands:
    def __init__(self, state, works=("ax", "mouse")):
        self.pressed, self.state, self.works = [], state, works

    def press(self, el, app, bid, confirmed=False, mouse=False):
        self.pressed.append((el.ref, mouse))
        if ("mouse" if mouse else "ax") in self.works:
            self.state["playing"] = True
        return "нажала"


opened = []
r = recipes.find("включи кино группа крови в ютуб музыке")
t = [0.0]


def clock():
    return t[0]


def sleep(s):
    t[0] += s


def go(recipe, eyes_, hands_, timeout=8):
    t[0] = 0.0
    return recipes.run(recipe, eyes_, hands_, opened.append, timeout=timeout, sleep=sleep, clock=clock)


st = {"playing": False}
h = Hands(st)
ok = go(r, Eyes(3, st), h)
if not ok or h.pressed != [("p0", False)] or opened[-1] != r.url:
    bad.append(f"кнопка на 3-м снимке: ok={ok} pressed={h.pressed}")
st = {"playing": False}
h = Hands(st, works=("mouse",))
ok = go(r, Eyes(2, st), h)
if not ok or h.pressed != [("p0", False), ("p0", True)]:
    bad.append(f"не заиграло — мышью: ok={ok} pressed={h.pressed}")
st = {"playing": False}
h = Hands(st, works=())
ok = go(r, Eyes(2, st), h)
if ok:
    bad.append("не заиграло ни так, ни мышью — а сказала «получилось»")
st = {"playing": True}
h = Hands(st, works=())
ok = go(r, Eyes(2, st), h)
if not ok or len(h.pressed) != 1:
    bad.append(f"уже что-то играло — одного нажатия хватит: ok={ok} pressed={h.pressed}")
st = {"playing": False}
h = Hands(st)
ok = go(recipes.find("включи новый мерин в ютуб музыке"),
        Eyes(2, st, labels=("Play MORGENSHTERN", "Play Новый Мерин - MORGENSHTERN")), h)
if h.pressed[:1] != [("p1", False)]:
    bad.append(f"выбрана не та кнопка: {h.pressed}")
st = {"playing": False}
h = Hands(st)
ok = go(r, Eyes(None, st), h)
if ok or h.pressed or t[0] < 8:
    bad.append(f"кнопка не появилась: ok={ok} pressed={h.pressed} t={t[0]}")
h = Hands(st)
ok = go(recipes.find("найди наушники на купанге"), Eyes(None, st), h)
if not ok or h.pressed:
    bad.append("купанг: только открыть")

if bad:
    print("\n".join(bad))
    sys.exit(1)
print("OK")
