"""Инициатива: она сама начинает разговор.
- напоминания по просьбе («напомни через 10 минут…», «напомни в 18:30…»);
- вечером спрашивает, как прошёл день (раз в день, если не спит);
- после долгой тишины сама заговаривает (не чаще раза в 45 минут, не ночью).
Во время игр (пауза) и во сне — молчит; напоминания ждут конца паузы."""
import json
import re
import threading
import time
from datetime import datetime, timedelta

from journal import now

_ABS = re.compile(r"НАПОМНИТЬ\s+(\d{1,2})[:.](\d{2})\s*\|\s*(.+)", re.I | re.S)
_REL = re.compile(r"НАПОМНИТЬ\s+\+\s*(\d{1,4})\s*\|\s*(.+)", re.I | re.S)


def parse_reminder(cmd: str, at: datetime | None = None) -> dict | None:
    at = at or now()
    m = _REL.match(cmd.strip())
    if m:
        return {"at": (at + timedelta(minutes=int(m.group(1)))).isoformat(timespec="seconds"),
                "text": m.group(2).strip()}
    m = _ABS.match(cmd.strip())
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            return None
        t = at.replace(hour=h, minute=mi, second=0, microsecond=0)
        if t <= at:
            t += timedelta(days=1)            # «в 8:00», а сейчас уже вечер — значит завтра
        return {"at": t.isoformat(timespec="seconds"), "text": m.group(3).strip()}
    return None


def _in_quiet(t: datetime, quiet: str) -> bool:
    """quiet = '23:30-09:00'."""
    try:
        a, b = quiet.split("-")
        ah, am = map(int, a.split(":"))
        bh, bm = map(int, b.split(":"))
    except ValueError:
        return False
    cur = t.hour * 60 + t.minute
    start, end = ah * 60 + am, bh * 60 + bm
    return (cur >= start or cur < end) if start > end else (start <= cur < end)


class Initiative:
    def __init__(self, companion, cfg: dict):
        self.c = companion
        i = cfg.get("initiative", {})
        self.enabled = i.get("enabled", True)
        self.idle_min = i.get("idle_minutes", 20)
        self.gap_min = i.get("min_gap_minutes", 45)
        self.quiet = i.get("quiet_hours", "23:30-09:00")
        self.evening = i.get("evening", "21:30")
        self.path = cfg["_data_dir"] / "reminders.json"
        self.last_initiative = time.monotonic()
        self.evening_done_on = None
        self._lock = threading.Lock()

    # --- напоминания ---
    def _load(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return []

    def _save(self, items: list[dict]) -> None:
        self.path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_from_command(self, cmd: str) -> dict | None:
        r = parse_reminder(cmd)
        if not r:
            print(f"[напоминание] не поняла команду: {cmd}")
            return None
        with self._lock:
            items = self._load()
            items.append(r)
            self._save(items)
        when = datetime.fromisoformat(r["at"]).strftime("%H:%M")
        print(f"[напоминание] в {when}: {r['text']}")
        self.c.ui.add("sys", f"⏰ Напомню в {when}: {r['text']}")
        self.c.journal.log("reminder_set", at=r["at"], text=r["text"])
        return r

    def pending(self) -> list[dict]:
        return self._load()

    def _due(self) -> list[dict]:
        t = now()
        with self._lock:
            items = self._load()
            due = [r for r in items if datetime.fromisoformat(r["at"]) <= t]
            if due:
                self._save([r for r in items if r not in due])
        return due

    # --- цикл ---
    def _can_speak(self) -> bool:
        c = self.c
        return (c.ready.is_set() and not c.pauser.paused and not c.speaking
                and not c.busy.locked())

    def tick(self) -> None:
        c = self.c
        if not c.ready.is_set() or c.pauser.paused:
            return
        # 1) напоминания — даже если она спит (ты сам попросил)
        for r in self._due():
            print(f"⏰ напоминание: {r['text']}")
            c.journal.log("reminder", text=r["text"])
            if getattr(c, "tg", None):
                c.tg.send_owner(f"⏰ {r['text']}")
            c.say_generated(c.system(), f"Мягко напомни {c.user}: «{r['text']}». Одной-двумя фразами.",
                            fallback=f"Напоминаю: {r['text']}")
            self.last_initiative = time.monotonic()
        if not self.enabled or not c.awake or not self._can_speak():
            return
        t = now()
        if _in_quiet(t, self.quiet):
            return
        # 2) вечером — как прошёл день (раз в день)
        eh, em = map(int, self.evening.split(":"))
        if (self.evening_done_on != t.date() and (t.hour, t.minute) >= (eh, em)
                and time.monotonic() - c.last_talk > 5 * 60):
            self.evening_done_on = t.date()
            self._start("Уже вечер. Тепло и коротко спроси, как прошёл его день.")
            return
        # 3) после долгой тишины — сама заговаривает
        idle = time.monotonic() - c.last_talk
        since_last = time.monotonic() - self.last_initiative
        if idle > self.idle_min * 60 and since_last > self.gap_min * 60:
            self._start("Вы давно молчите. Сама начни коротенький разговор: спроси что-то простое "
                        "про его дела или скажи что-то тёплое. Не повторяй то, что уже говорила.")

    def _start(self, instruction: str) -> None:
        self.last_initiative = time.monotonic()
        print("💬 заговариваю первой")
        self.c.journal.log("initiative")
        self.c.say_generated(self.c.system(), instruction)
        self.c.last_talk = time.monotonic()

    def run(self) -> None:
        while True:
            time.sleep(10)
            try:
                self.tick()
            except Exception as e:
                print(f"[инициатива] {e}")
