"""Рецепты «глаз и рук»: частые просьбы — быстро, без долгих раздумий мозга.
«Включи <песня> в ютуб музыке» → открыть поиск YouTube Music → дождаться кнопки «Воспроизвести» → нажать.
«Найди на ютубе …» → поиск YouTube → открыть первое видео. «Найди … на купанге / в навере / загугли …» —
только открыть поиск. Не вышло за ~8 с — задачу продолжает агент (agent.py)."""
import re
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote

from intents import norm

PLAY_WORDS = ("воспроизвести", "play", "재생", "слушать")
VERBS = {"включи", "включай", "включить", "поставь", "поставить", "найди", "найти", "покажи", "запусти", "сыграй",
         "играй", "поищи", "открой", "play", "find", "search", "put", "show", "загугли", "погугли"}
FILLER = {"песню", "песня", "трек", "пожалуйста", "мне", "плиз", "please", "on", "in", "аня", "алиса", "таня",
          "подруга", "можешь", "давай", "а", "ну", "the", "song", "me"}
KO_VERBS = ("틀어", "찾아", "재생", "보여", "켜줘", "검색", "들려")
PRE = r"(?:\b(?:в|на|on|in)\s+)?"


@dataclass
class Recipe:
    name: str
    url: str
    target: Callable | None = None


def _is_play(el) -> bool:
    lab = norm(el.label)
    return el.role == "AXButton" and lab.startswith(PLAY_WORDS)


def _is_video(el) -> bool:
    lab = norm(el.label)
    return (el.role == "AXLink" and len(lab) >= 15
            and not re.search(r"\b(реклама|ad|ads|shorts|канал|channel|подписаться|광고)\b", lab))


SITES = [   # (имя, шаблон, ссылка, цель, нужен ли глагол)
    ("ytmusic", PRE + r"(?:ютуб\w*|ютьюб\w*|youtube|yt)\s*(?:музык\w*|music)|유튜브\s*뮤직(?:에서|으로|로)?",
     "https://music.youtube.com/search?q=", _is_play, True),
    ("youtube", PRE + r"(?:ютуб\w*|ютьюб\w*|youtube)|유튜브(?:에서|로)?",
     "https://www.youtube.com/results?search_query=", _is_video, True),
    ("coupang", PRE + r"(?:купанг\w*|coupang)|쿠팡(?:에서)?", "https://www.coupang.com/np/search?q=", None, True),
    ("naver", PRE + r"(?:навер\w*|naver)|네이버(?:에서)?", "https://search.naver.com/search.naver?query=", None, True),
    ("google", r"\b(?:за|по)гугли\b|" + PRE + r"(?:гугл\w*|google)|구글(?:에서)?",
     "https://www.google.com/search?q=", None, True),
]


def _query(rest: str) -> str:
    words = [w for w in rest.split() if w not in VERBS and w not in FILLER and not any(k in w for k in KO_VERBS)]
    return " ".join(words).strip()


def find(goal: str) -> Recipe | None:
    t = norm(goal)
    if not t:
        return None
    words = set(t.split())
    has_verb = bool(words & VERBS) or any(k in t for k in KO_VERBS) or re.search(r"\b(?:за|по)гугли\b", t)
    for name, pattern, url, target, need_verb in SITES:
        m = re.search(pattern, t)
        if not m:
            continue
        if need_verb and not has_verb:
            return None
        q = _query((t[:m.start()] + " " + t[m.end():]).strip())
        if not q:
            return None
        return Recipe(name, url + quote(q), target)
    return None


def run(r: Recipe, eyes_mod, hands_mod, open_fn, timeout: float = 8.0, sleep=time.sleep,
        clock=time.monotonic) -> bool:
    """Открыть и (если есть цель) нажать её. True — получилось."""
    open_fn(r.url)
    if r.target is None:
        return True
    end = clock() + timeout
    sleep(1.0)                                   # страница начинает грузиться
    while clock() < end:
        snap = eyes_mod.snapshot()
        el = next((e for e in snap.elements if r.target(e)), None)
        if el is not None:
            hands_mod.press(el, snap.app, snap.bundle_id)
            return True
        sleep(0.5)
    return False
