"""Привычки: она замечает, что он делает примерно в одно время, и сама предлагает.
Каждая его просьба «включи / открой / запусти / режим …», которую она выполнила, записывается с временем.
Если то же самое было в похожее время (от 15 минут раньше до 45 минут позже, чем сейчас) хотя бы в 3 разных
дня за последние 3 недели, а сегодня ещё не было — она спрашивает: «Ты обычно в это время просишь
«включи лоу-фай». Сделать?». Только предлагает: делает лишь после «да». Дважды подряд «нет» — молчит
об этом 2 недели, «больше не предлагай» — навсегда. Не чаще раза в день на одну привычку.
Хранится в data/habits.json — только на этом Mac."""
import json
import re
import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from intents import norm

START = re.compile(r"^(?:(?:подруга|аня|ань|алиса|таня|давай|пожалуйста)\s+)*"
                   r"(включи|открой|запусти|поставь|зайди|найди и включи|play|open|start|켜|틀어|열어)\b")
NOT_HABIT = re.compile(r"(пауз|стоп|выключ|закр|громк|громч|тише|потиш|скрин|таймер|напомн|экран|переведи|прочитай|"
                       r"перескажи|папк|файл|режим english|по-английски|по-корейски)")
MIN_DAYS = 3             # столько разных дней — уже привычка
LOOKBACK = 21            # дней
EARLY, LATE = 15, 45     # минут: «в это время» — чуть раньше обычного и до 45 минут позже
KEEP_DAYS = 60
SAME = 0.88              # «включи лоу фай» и «включи лоуфай» — одно и то же


def _mins(t: datetime) -> int:
    return t.hour * 60 + t.minute


def _near_time(m: int, cur: int) -> bool:
    d = (m - cur) % 1440            # насколько обычное время позже текущего (по кругу суток)
    return d <= LATE or 1440 - d <= EARLY


class Habits:
    def __init__(self, path: Path, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        try:
            d = json.loads(self.path.read_text("utf-8"))
        except Exception:
            d = {}
        self.log: list[dict] = d.get("log", [])
        self.muted: dict[str, float] = d.get("muted", {})      # ключ → до какого времени (0 — навсегда)
        self.offered: dict[str, str] = d.get("offered", {})    # ключ → дата последнего предложения
        self.declines: dict[str, int] = d.get("declines", {})

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"log": self.log, "muted": self.muted, "offered": self.offered,
                                         "declines": self.declines}, ensure_ascii=False, indent=1), "utf-8")

    def _key(self, phrase: str) -> str:
        n = norm(phrase)
        for e in reversed(self.log):          # похожее уже было — тот же ключ
            if e["k"] == n or SequenceMatcher(None, e["k"], n).ratio() >= SAME:
                return e["k"]
        return n

    @staticmethod
    def is_habit_like(phrase: str) -> bool:
        n = norm(phrase)
        return bool(n) and len(n.split()) <= 10 and bool(START.match(n)) and not NOT_HABIT.search(n)

    def note(self, phrase: str, mode: bool = False) -> bool:
        """Он попросил — она сделала. mode=True — это его режим («рабочий режим»), записываем всегда."""
        if not phrase or not (mode or self.is_habit_like(phrase)):
            return False
        now = self.clock()
        k = self._key(phrase)
        self.log.append({"k": k, "p": phrase.strip(), "t": int(now)})
        border = now - KEEP_DAYS * 86400
        self.log = [e for e in self.log if e["t"] >= border][-3000:]
        self._write()
        return True

    def suggestion(self, at: datetime | None = None):
        """(ключ, его фраза, в скольких днях) — что предложить прямо сейчас, или None."""
        at = at or datetime.fromtimestamp(self.clock())
        today = at.date()
        cur = _mins(at)
        start = (at - timedelta(days=LOOKBACK)).timestamp()
        groups: dict[str, list[dict]] = {}
        for e in self.log:
            if e["t"] >= start:
                groups.setdefault(e["k"], []).append(e)
        best = None
        for k, es in groups.items():
            until = self.muted.get(k)
            if until is not None and (until == 0 or until > at.timestamp()):
                continue
            if self.offered.get(k) == today.isoformat():
                continue
            days = {datetime.fromtimestamp(e["t"]).date() for e in es}
            if today in days:                       # сегодня уже делал — не напоминаем
                continue
            near = {datetime.fromtimestamp(e["t"]).date() for e in es
                    if _near_time(_mins(datetime.fromtimestamp(e["t"])), cur)}
            if len(near) >= MIN_DAYS and (best is None or len(near) > best[2]):
                last = max(es, key=lambda e: e["t"])
                best = (k, last["p"], len(near))
        return best

    def mark_offered(self, key: str, at: datetime | None = None) -> None:
        at = at or datetime.fromtimestamp(self.clock())
        self.offered[key] = at.date().isoformat()
        self._write()

    def answer(self, key: str, yes: bool) -> None:
        if yes:
            self.declines.pop(key, None)
        else:
            self.declines[key] = self.declines.get(key, 0) + 1
            if self.declines[key] >= 2:             # два «нет» подряд — две недели не предлагает
                self.muted[key] = self.clock() + 14 * 86400
                self.declines.pop(key, None)
        self._write()

    def mute(self, key: str) -> None:
        self.muted[key] = 0
        self._write()

    def describe(self, at: datetime | None = None) -> list[str]:
        """Что она заметила: «включи лоу-фай — обычно около 21:00 (5 дн.)»."""
        at = at or datetime.fromtimestamp(self.clock())
        start = (at - timedelta(days=LOOKBACK)).timestamp()
        groups: dict[str, list[dict]] = {}
        for e in self.log:
            if e["t"] >= start:
                groups.setdefault(e["k"], []).append(e)
        out = []
        for k, es in groups.items():
            ms = sorted(_mins(datetime.fromtimestamp(e["t"])) for e in es)
            mid = ms[len(ms) // 2]
            near = {datetime.fromtimestamp(e["t"]).date() for e in es
                    if _near_time(_mins(datetime.fromtimestamp(e["t"])), (mid - 15) % 1440)}
            if len(near) >= MIN_DAYS and self.muted.get(k) != 0:
                out.append(f"«{es[-1]['p']}» — обычно около {mid // 60:02d}:{mid % 60:02d}")
        return out

    def forget_all(self) -> int:
        n = len(self.log)
        self.log, self.muted, self.offered, self.declines = [], {}, {}, {}
        self._write()
        return n


_NEVER = re.compile(r"(больше\s+не\s+предлагай|не\s+предлагай|не\s+надо\s+предлагать|не\s+спрашивай\s+больше)")


def never(text: str) -> bool:
    return bool(_NEVER.search(norm(text)))
