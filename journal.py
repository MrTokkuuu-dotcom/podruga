"""Журнал событий. Пишет только программа (не ИИ) и только добавляет строки."""
import json
from datetime import datetime
from pathlib import Path


def now() -> datetime:
    return datetime.now().astimezone()


def format_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h} ч {m} мин"
    if h:
        return f"{h} ч"
    if m:
        return f"{m} мин"
    return "меньше минуты"


class Journal:
    def __init__(self, path: Path, user_name: str = "пользователь"):
        self.path = Path(path)
        self.user = user_name
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, kind: str, **data) -> dict:
        ev = {"ts": now().isoformat(timespec="seconds"), "kind": kind, **data}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return ev

    def read(self, limit: int | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        events = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # битая строка (например, выключили свет посреди записи)
        return events[-limit:] if limit else events

    def last(self, *kinds: str) -> dict | None:
        for ev in reversed(self.read()):
            if not kinds or ev["kind"] in kinds:
                return ev
        return None

    def describe(self, ev: dict) -> str:
        t = datetime.fromisoformat(ev["ts"]).strftime("%d.%m %H:%M")
        kind = ev["kind"]
        if kind == "app_start":
            text = "программа запущена"
        elif kind == "app_stop":
            text = "программа выключена"
        elif kind == "pause":
            reason = ev.get("reason")
            if reason == "game":
                text = f"пауза: {self.user} запустил {ev.get('detail')}"
            elif reason == "gpu":
                text = f"пауза: видеокарта занята ({ev.get('detail')})"
            elif reason == "hotkey":
                text = "пауза: включена вручную"
            else:
                text = "пауза"
        elif kind == "resume":
            text = f"вернулась, не было {format_duration(ev.get('away_sec', 0))}"
        elif kind == "conversation":
            text = f"разговор: {ev.get('summary', '')}"
        else:
            text = kind
        return f"{t} — {text}"

    def render(self, limit: int = 15) -> str:
        return "\n".join(self.describe(e) for e in self.read(limit))


class LastSeen:
    """Когда программа последний раз была жива. Нужно, если компьютер выключили,
    не закрыв программу: тогда в журнале нет 'app_stop', а тут время есть."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def touch(self) -> None:
        self.path.write_text(now().isoformat(timespec="seconds"), encoding="utf-8")

    def get(self) -> datetime | None:
        try:
            return datetime.fromisoformat(self.path.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError):
            return None
