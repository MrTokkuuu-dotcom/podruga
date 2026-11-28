"""Самообучение на его поправках.
1) «Нет, я имел в виду ютуб музыку» — сразу после её действия: она переделывает и запоминает,
   что его прошлая фраза значит вот это («включи музыку» → «включи ютуб музыку»). Дальше эта фраза
   сама заменяется на правильную, ещё до всех команд.
2) «Не называй меня зайкой», «не говори так», «говори короче», «запомни правило: …» — правило,
   которое попадает в подсказку обоим мозгам (свой и Google) и действует всегда.
«Чему ты научилась», «забудь это правило», «забудь, чему научилась». Хранится в data/lessons.json."""
import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

from intents import norm

MAX_RULES = 30
ACTION = re.compile(r"\b(откр|включ|запуст|закр|выключ|сдела|постав|найд|покаж|громк|тише|пауз|скрин|переключ|"
                    r"найти|play|open|turn|start|close)")
_NAMES = r"(?:(?:подруга|аня|ань|алиса|таня)\s+)?"

_MEANT = re.compile(r"^" + _NAMES + r"(?:нет|не то|не так|неправильно|да нет)?\s*(?:же\s+)?(?:я\s+)?"
                    r"(?:имел|имела|имею)\s+в\s+виду\s+(.{2,80})$")
_WANTED = re.compile(r"^" + _NAMES + r"(?:нет|не то|да нет)\s+(?:я\s+)?(?:же\s+)?(?:хотел|хотела|просил|просила)\s+"
                     r"(?:чтобы\s+ты\s+)?(.{2,80})$")
_NOT_THAT = re.compile(r"^" + _NAMES + r"(?:нет\s+)?не то\s+(.{3,80})$")

_RULES = [
    (re.compile(r"^" + _NAMES + r"(?:больше\s+|никогда\s+)?не\s+называй\s+меня\s+(.{2,40})$"),
     lambda m, her: f"Не называй его «{m.group(1)}»."),
    (re.compile(r"^" + _NAMES + r"(?:теперь\s+)?называй\s+меня\s+(.{2,40})$"),
     lambda m, her: f"Называй его «{m.group(1)}»."),
    (re.compile(r"^" + _NAMES + r"(?:больше\s+не\s+говори|не\s+говори\s+больше|не\s+говори)\s+(?:мне\s+)?так(?:\s+больше)?$"),
     lambda m, her: f"Не говори так, как сказала тут: «{her}»." if her else None),
    (re.compile(r"^" + _NAMES + r"(?:больше\s+не\s+говори|никогда\s+не\s+говори|не\s+говори\s+больше)\s+(?:мне\s+)?(.{2,60})$"),
     lambda m, her: f"Больше не говори ему: «{m.group(1)}»."),
    (re.compile(r"^" + _NAMES + r"(?:говори|отвечай)\s+(?:мне\s+)?(?:по[\s-])?(покороче|короче|проще|попроще|подробнее|"
                r"длиннее|медленнее|спокойнее|веселее|нежнее|серьезнее|честнее)(?:\s+.{0,30})?$"),
     lambda m, her: f"Отвечай {m.group(1)}."),
    (re.compile(r"^" + _NAMES + r"мне\s+не\s+нравится\s+когда\s+ты\s+(.{3,60})$"),
     lambda m, her: f"Ему не нравится, когда ты {m.group(1)} — не делай так."),
    (re.compile(r"^" + _NAMES + r"запомни\s+(?:новое\s+|такое\s+)?правило\s+(.{3,120})$"),
     lambda m, her: m.group(1)[0].upper() + m.group(1)[1:] + "."),
]
_LIST = re.compile(r"(чему|что)\s+ты\s+(уже\s+)?(на)?училась|какие\s+у\s+тебя\s+правила|что\s+ты\s+выучила")
_FORGET_ONE = re.compile(r"^" + _NAMES + r"(?:забудь|отмени|удали)\s+(?:это|последнее|прошлое)\s+(?:правило|урок)$")
_FORGET_ALL = re.compile(r"^" + _NAMES + r"(?:забудь|сотри)\s+(?:всё|все)?\s*(?:чему\s+(?:ты\s+)?научилась|"
                         r"все\s+правила|всё\s+выученное|все\s+выученное)$")


def _clean(text: str) -> str:
    return norm(text).strip()


def _verb(text: str) -> str:
    w = text.split()
    return next((x for x in w if ACTION.match(x)), "")


class Lessons:
    def __init__(self, path: Path):
        self.path = Path(path)
        try:
            d = json.loads(self.path.read_text("utf-8"))
        except Exception:
            d = {}
        self.rules: list[dict] = d.get("rules", [])
        self.aliases: dict[str, str] = d.get("aliases", {})
        self._last = None             # ("rule", i) | ("alias", ключ) — для «забудь это правило»

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"rules": self.rules, "aliases": self.aliases}, ensure_ascii=False,
                                        indent=1), "utf-8")

    # --- запоминание ---
    def add_rule(self, text: str) -> bool:
        n = norm(text)
        if any(norm(r["text"]) == n for r in self.rules):
            return False
        self.rules.append({"text": text, "t": int(time.time())})
        self.rules = self.rules[-MAX_RULES:]
        self._last = ("rule", len(self.rules) - 1)
        self._write()
        return True

    def add_alias(self, said: str, meant: str) -> None:
        self.aliases[_clean(said)] = meant
        self._last = ("alias", _clean(said))
        self._write()

    def forget_last(self) -> str | None:
        if self._last is None:                    # после перезапуска — просто самое новое правило
            self._last = ("rule", len(self.rules) - 1) if self.rules else None
            if self._last is None:
                return None
        kind, k = self._last
        self._last = None
        if kind == "rule" and 0 <= k < len(self.rules):
            t = self.rules.pop(k)["text"]
        elif kind == "alias" and k in self.aliases:
            t = f"«{k}» — это «{self.aliases.pop(k)}»"
        else:
            return None
        self._write()
        return t

    def forget_all(self) -> int:
        n = len(self.rules) + len(self.aliases)
        self.rules, self.aliases, self._last = [], {}, None
        self._write()
        return n

    # --- применение ---
    def rewrite(self, text: str) -> str:
        """Его фраза, которую он раньше поправлял, → то, что он на самом деле имеет в виду."""
        t = _clean(text)
        if not t or not self.aliases:
            return text
        if t in self.aliases:
            return self.aliases[t]
        for k, v in self.aliases.items():
            # опечатки распознавания — да, но «выключи» ≠ «включи»: первое слово должно совпасть
            if len(k) >= 6 and t.split()[0] == k.split()[0] and SequenceMatcher(None, t, k).ratio() >= 0.9:
                return v
        return text

    def prompt_block(self, user: str = "он") -> str:
        if not self.rules:
            return ""
        return (f"## Правила, которым {user} тебя научил (выполняй всегда, важнее остального)\n"
                + "\n".join(f"- {r['text']}" for r in self.rules))

    def describe(self) -> list[str]:
        out = [r["text"] for r in self.rules]
        out += [f"«{k}» — это «{v}»" for k, v in self.aliases.items()]
        return out


def command(text: str, prev_user: str | None, prev_her: str | None, prev_action: bool):
    """('meant', правильная фраза) | ('rule', текст) | ('list',) | ('forget',) | ('forget_all',) | None.
    prev_action — её прошлый ответ был делом (открыла / включила / нажала), а не разговором."""
    t = _clean(text)
    if not t or len(t.split()) > 16:
        return None
    if _LIST.search(t):
        return ("list",)
    if _FORGET_ONE.match(t):
        return ("forget",)
    if _FORGET_ALL.match(t):
        return ("forget_all",)
    if prev_user and prev_action:
        for rx in (_MEANT, _WANTED, _NOT_THAT):
            m = rx.match(t)
            if m:
                meant = m.group(1).strip()
                if not ACTION.search(meant):                     # «ютуб музыку» → «включи ютуб музыку»
                    v = _verb(_clean(prev_user))
                    if not v:
                        return None
                    meant = f"{v} {meant}"
                if _clean(meant) == _clean(prev_user):
                    return None
                return ("meant", meant)
    her = (prev_her or "").strip()
    for rx, make in _RULES:
        m = rx.match(t)
        if m:
            r = make(m, her[:160])
            if r:
                return ("rule", r)
    return None
