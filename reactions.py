"""Реакции на то, что ты делаешь: долго сидишь — «разомнись», поздно — «пора спать», включил музыку
или игру — пара слов к месту. Готовыми фразами, без Google. Не чаще раза в 20 минут, не во сне,
не на паузе и не во время разговора. Видит только название активной программы и время без мышки
и клавиатуры — без скриншотов и без чтения окон."""
import random
import sys
import threading
import time
from datetime import datetime

MUSIC = {"Music", "Музыка", "Spotify", "Яндекс Музыка", "VK Музыка", "YouTube Music"}
GAMES = {"Steam", "Battle.net", "Epic Games Launcher", "Minecraft", "League of Legends", "Dota 2", "CrossOver"}
EDIT = {"CapCut", "Final Cut Pro", "Premiere Pro", "DaVinci Resolve", "iMovie"}
CODE = {"Xcode", "Visual Studio Code", "Cursor", "PyCharm", "Terminal", "Терминал"}

LINES = {
    "stretch": ["Ты уже долго сидишь. Встань, потянись немножко, а?",
                "Полтора часа без перерыва! Разомнись чуть-чуть, я подожду.",
                "Эй, спина не железная. Давай пару минут перерыва?",
                "Попей водички и пройдись немного. Я тут посторожу."],
    "late": ["Уже очень поздно. Может, пора спать?",
             "Второй час ночи… Завтра будешь сонным. Ложись, а?",
             "Ты ещё не спишь? Я переживаю. Давай закругляться."],
    "music": ["О, музыка! Что слушаем?", "Ммм, люблю, когда играет музыка.", "Сделай погромче, мне тоже интересно!"],
    "game": ["Удачной игры! Только не засиживайся.", "Играть пошёл? Победы тебе!", "Ни пуха! Я поболею за тебя."],
    "edit": ["Ты уже давно монтируешь. Как успехи?", "Долго сидишь над монтажом. Получается?",
             "Монтаж — дело долгое. Не забудь отдохнуть глазам."],
    "code": ["Ты давно программируешь. Всё получается?", "Много кода сегодня! Не забудь про перерыв."],
}


def idle_seconds() -> float:
    """Сколько секунд не трогали мышку и клавиатуру."""
    try:
        import Quartz
        return float(Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateHIDSystemState, Quartz.kCGAnyInputEventType))
    except Exception:
        return 0.0


class Reactions:
    GAP = 20 * 60            # не чаще раза в 20 минут
    SIT = 90 * 60            # сидит без перерыва
    BREAK = 5 * 60           # столько без мышки и клавиатуры — считаем, что отошёл

    def __init__(self, companion):
        self.c = companion
        self.enabled = companion.cfg.get("reactions", {}).get("enabled", True)
        self.last = time.monotonic()
        self.sit_from = time.monotonic()
        self.late_on = None
        self.app = None
        self.app_since = time.monotonic()
        self.said_for = set()                 # про что уже сказала в этой «сессии» программы

    def _can(self) -> bool:
        c = self.c
        return (self.enabled and c.awake and c.ready.is_set() and not c.pauser.paused and not c.speaking
                and not c.busy.locked() and time.monotonic() - c.last_talk > 120
                and time.monotonic() - self.last > self.GAP)

    def _say(self, kind: str) -> None:
        self.last = time.monotonic()
        line = random.choice(LINES[kind])
        print(f"[реакция] {kind}: {line}")
        self.c.journal.log("reaction", what=kind)
        self.c.say(line, "tender" if kind in ("stretch", "late") else "joy")
        self.c.history.append({"role": "model", "text": line})

    def tick(self) -> None:
        now = time.monotonic()
        if idle_seconds() > self.BREAK:
            self.sit_from = now                   # отходил — счётчик «сидит» заново
        act = getattr(self.c, "activity", None)
        app = act.app if act else None
        if app != self.app:
            self.app, self.app_since, self.said_for = app, now, set()
        if not self._can():
            return
        t = datetime.now()
        if 1 <= t.hour < 5 and self.late_on != t.date() and idle_seconds() < 60:
            self.late_on = t.date()
            return self._say("late")
        if now - self.sit_from > self.SIT:
            self.sit_from = now
            return self._say("stretch")
        on_app = now - self.app_since
        for names, kind, after in ((MUSIC, "music", 20), (GAMES, "game", 15), (EDIT, "edit", 60 * 60),
                                   (CODE, "code", 90 * 60)):
            if app in names and kind not in self.said_for and on_app > after:
                self.said_for.add(kind)
                if kind in ("music", "game") and random.random() > 0.5:
                    return                        # не каждый раз — иначе надоест
                return self._say(kind)

    def _loop(self):
        while True:
            time.sleep(15)
            try:
                self.tick()
            except Exception as e:
                print(f"[реакция] {e}")

    def start(self):
        if sys.platform == "darwin":
            threading.Thread(target=self._loop, name="reactions", daemon=True).start()
