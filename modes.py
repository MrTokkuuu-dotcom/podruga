"""Свои команды-«режимы»: «Запомни: рабочий режим — это открыть хром, почту и включить лоу-фай».
Потом «рабочий режим» (или «включи рабочий режим») — она делает шаги по очереди: каждый шаг идёт тем же
путём, что и обычная просьба (сразу / рецепт / сама на экране), с той же охраной.
Хранится в data/modes.json. «Забудь рабочий режим», «какие у тебя режимы»."""
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from intents import norm

ACTION = re.compile(r"\b(откр|включ|запуст|закр|выключ|сдела|постав|найд|покаж|громк|тише|пауз|скрин|переключ|"
                    r"найти|play|open|turn|start|close|켜|열어|틀어)")
_SAVE = re.compile(r"^(?:запомни|запиши|сохрани|remember)\s+(?:что\s+|режим\s+|команду\s+)?(.{2,40}?)\s+"
                   r"(?:это|значит|означает|будет|is|means)\s+(.+)$")
_SAVE_WHEN = re.compile(r"^(?:запомни\s+)?когда\s+я\s+(?:говорю|скажу)\s+(.{2,40}?)\s+(?:то\s+|ты\s+)*(.+)$")
_FORGET = re.compile(r"^(?:забудь|удали|сотри|forget)\s+(?:режим\s+|команду\s+)?(.{2,40})$")
_LIST = re.compile(r"(какие|какой|покажи|перечисли|назови)\s+(у тебя\s+)?(есть\s+)?(мои\s+)?(режимы|команды)|"
                   r"list (my )?modes")
_FILLER = r"\b(пожалуйста|please|подруга|ань|аня|алиса|таня|давай|можешь|ну|а|ка)\b"
_SPLIT = re.compile(r"\s*(?:,|;|\bи потом\b|\bпотом\b|\bзатем\b|\bа ещ[её]\b|\bи\b|\band\b|\bthen\b)\s*")


def _clean(text: str) -> str:
    return " ".join(re.sub(_FILLER, " ", norm(text)).split())


def split_steps(text: str) -> list[str]:
    """«открыть хром, почту и включить лоу-фай» → [«открыть хром», «открыть почту», «включить лоу-фай»]."""
    parts = [p.strip(" .") for p in _SPLIT.split(text) if p and p.strip(" .")]
    out, verb = [], ""
    for p in parts:
        first = p.split()[0]
        if ACTION.match(first):
            verb = first
            out.append(p)
        elif verb:                                    # «почту» после «открыть хром» — тоже открыть
            out.append(f"{verb} {p}")
        else:
            out.append(p)
    return out


def _imperative(step: str) -> str:
    """«открыть хром» → «открой хром» — так шаг понимают остальные части (intents, рецепты)."""
    w = step.split()
    if not w:
        return step
    swap = {"открыть": "открой", "включить": "включи", "запустить": "запусти", "закрыть": "закрой",
            "выключить": "выключи", "сделать": "сделай", "поставить": "поставь", "найти": "найди",
            "показать": "покажи", "переключить": "переключи"}
    w[0] = swap.get(w[0], w[0])
    return " ".join(w)


def parse_save(text: str):
    """(имя, [шаги]) или None — только если в шагах есть действия (иначе это обычное «запомни» про жизнь)."""
    t = re.sub(r"[—–:!?«»\"]", " ", text.lower().replace("ё", "е"))
    t = " ".join(t.replace(".", " ").split())
    for rx in (_SAVE, _SAVE_WHEN):
        m = rx.search(t)
        if not m:
            continue
        name = _clean(m.group(1).strip(" ,")).strip()
        name = re.sub(r"^(режим|команда)\s+", "", name)
        steps = [_imperative(s) for s in split_steps(m.group(2).strip(" ,"))]
        if name and len(name.split()) <= 4 and steps and all(ACTION.search(s) for s in steps):
            return name, steps[:8]
    return None


class Modes:
    def __init__(self, path: Path):
        self.path = Path(path)
        try:
            self.items = json.loads(self.path.read_text("utf-8"))
        except Exception:
            self.items = {}

    def save(self, name: str, steps: list[str]) -> None:
        self.items[name] = steps
        self._write()

    def forget(self, name: str) -> str | None:
        key = self.match(name, loose=True)
        if key:
            self.items.pop(key, None)
            self._write()
        return key

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), "utf-8")

    def match(self, text: str, loose: bool = False) -> str | None:
        """Имя режима, если фраза — это он («рабочий режим», «включи рабочий режим», «режим рабочий»)."""
        t = _clean(text)
        if not t or not self.items:
            return None
        t = re.sub(r"^(включи|запусти|давай|сделай|start|run)\s+", "", t)
        cands = {t, re.sub(r"\s*режим$", "", t), re.sub(r"^режим\s*", "", t)}
        best, score = None, 0.0
        for name in self.items:
            n = name
            forms = {n, re.sub(r"\s*режим$", "", n), re.sub(r"^режим\s*", "", n)}
            for a in cands:
                for b in forms:
                    if not a or not b:
                        continue
                    r = 1.0 if a == b else SequenceMatcher(None, a, b).ratio()
                    if r > score:
                        best, score = name, r
        return best if score >= (0.8 if loose else 0.9) else None


def command(text: str, modes: Modes):
    """('save', имя, шаги) | ('forget', имя) | ('list',) | ('run', имя) | None."""
    s = parse_save(text)
    if s:
        return ("save", s[0], s[1])
    t = norm(text)
    m = _FORGET.search(t)
    if m and modes.match(m.group(1), loose=True):
        return ("forget", m.group(1))
    if _LIST.search(t):
        return ("list",)
    name = modes.match(text)
    if name:
        return ("run", name)
    return None
