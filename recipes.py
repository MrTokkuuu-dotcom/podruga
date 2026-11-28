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
         "играй", "поищи", "открой", "посмотри", "глянь", "play", "watch", "find", "search", "put", "show", "загугли", "погугли"}
FILLER = {"песню", "песня", "трек", "пожалуйста", "мне", "плиз", "please", "аня", "алиса", "таня",
          "подруга", "можешь", "давай", "а", "ну", "какое-нибудь", "какой-нибудь", "какую-нибудь", "видео", "видос",
          "видосик", "видосики", "ролик", "про", "о", "об", "что-нибудь", "и", "любое", "любой", "любую", "любые",
          "канал", "канала", "каналу", "какое", "какую", "какой", "там", "уже", "сейчас", "ещё", "еще"}    # только по краям запроса: «Hate Me», «In the End» — целиком
KO_VERBS = ("틀어", "찾아", "재생", "보여", "켜줘", "검색", "들려")
PRE = r"(?:\b(?:в|на|on|in)\s+)?"


@dataclass
class Recipe:
    name: str
    url: str
    target: Callable | None = None
    query: str = ""
    verify: bool = False        # проверить, что заиграло (в плеере появилась «Пауза»)


def _is_play(el) -> bool:
    """Кнопка «Воспроизвести <название>» у результата. Голая «Воспроизвести» — это плеер внизу, не она."""
    lab = norm(el.label)
    if el.role != "AXButton" or not lab.startswith(PLAY_WORDS):
        return False
    rest = lab.split(" ", 1)[1] if " " in lab else ""
    return len(rest) >= 2


def _is_video(el) -> bool:
    lab = norm(el.label)
    return (el.role == "AXLink" and len(lab) >= 15
            and not re.search(r"\b(реклама|ad|ads|shorts|канал|channel|подписаться|광고)\b", lab))


SITES = [   # (имя, шаблон, ссылка, цель, нужен ли глагол)
    ("ytmusic", PRE + r"(?:ютуб\w*|ютьюб\w*|youtube|yt|этот|ют)\s*(?:музык\w*|music|мьюзик\w*)|"
     + PRE + r"(?<!эпл )(?<!apple )\bмьюзик\w*|유튜브\s*뮤직(?:에서|으로|로)?",
     "https://music.youtube.com/search?q=", _is_play, True),
    ("youtube", PRE + r"(?:ютуб\w*|ютьюб\w*|youtube)|유튜브(?:에서|로)?",
     "https://www.youtube.com/results?search_query=", _is_video, True),
    ("coupang", PRE + r"(?:купанг\w*|coupang)|쿠팡(?:에서)?", "https://www.coupang.com/np/search?q=", None, True),
    ("naver", PRE + r"(?:навер\w*|naver)|네이버(?:에서)?", "https://search.naver.com/search.naver?query=", None, True),
    ("google", r"\b(?:за|по)гугли\b|" + PRE + r"(?:гугл\w*|google)|구글(?:에서)?",
     "https://www.google.com/search?q=", None, True),
]


def _skip(w: str) -> bool:
    return w in VERBS or w in FILLER or any(k in w for k in KO_VERBS)


def _query(rest: str) -> str:
    words = rest.split()
    while words and _skip(words[0]):
        words.pop(0)
    while words and _skip(words[-1]):
        words.pop()
    return " ".join(words).strip()


def find(goal: str) -> Recipe | None:
    from intents import unjunk
    t = unjunk(norm(goal))                       # «короче, включи кино в ютуб музыке» — без «короче» в поиске
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
        rest = (t[:m.start()] + " " + t[m.end():]).split()
        first = next((i for i, w in enumerate(rest) if w in VERBS), None)
        if first:                                # «я говорю поставь …», «нет, я сказал включи …» — начало не в поиск
            rest = rest[first:]
        q = _query(" ".join(rest))
        if not q:
            return None
        return Recipe(name, url + quote(q), target, q, name == "ytmusic")
    return None


def _best(snap, r: Recipe):
    """Подходящая кнопка, в подписи которой больше всего слов из запроса (при равенстве — первая)."""
    cands = [e for e in snap.elements if r.target(e)]
    if not cands:
        return None
    words = set(norm(r.query).split())
    return max(cands, key=lambda e: (len(words & set(norm(e.label).split())), -cands.index(e)))


def _wait_playing(eyes_mod, sleep, clock, secs: float = 3.0) -> bool:
    end = clock() + secs
    while clock() < end:
        sleep(0.5)
        if eyes_mod.is_playing(eyes_mod.snapshot()):
            return True
    return False


def run(r: Recipe, eyes_mod, hands_mod, open_fn, timeout: float = 8.0, sleep=time.sleep,
        clock=time.monotonic) -> bool:
    """Открыть и (если есть цель) нажать её. True — получилось (для музыки — правда заиграло)."""
    open_fn(r.url)
    if r.target is None:
        return True
    end = clock() + timeout
    sleep(1.0)                                   # страница начинает грузиться
    while clock() < end:
        snap = eyes_mod.snapshot()
        el = _best(snap, r)
        if el is None:
            sleep(0.5)
            continue
        was_playing = r.verify and eyes_mod.is_playing(snap)
        print(f"[руки] жму «{el.label}»")
        hands_mod.press(el, snap.app, snap.bundle_id)
        if not r.verify or was_playing:           # уже что-то играло — по «Паузе» не отличить, верим нажатию
            return True
        if _wait_playing(eyes_mod, sleep, clock):
            return True
        print(f"[руки] «{el.label}» не заиграло — нажимаю мышью")
        hands_mod.press(el, snap.app, snap.bundle_id, mouse=True)
        return _wait_playing(eyes_mod, sleep, clock)
    return False
