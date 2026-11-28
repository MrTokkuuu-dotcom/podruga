"""Самообучение на удачных задачах. Когда она сама, шаг за шагом, что-то сделала на экране (агент своим мозгом,
20–40 с), записываем, ЧТО она нажимала и печатала — по подписям кнопок, не по координатам. В следующий раз
та же просьба повторяется по записи за пару секунд. Если просьба отличается только тем, что искать
(«включи Кино на ютубе» → «включи Сплин на ютубе»), запись подходит и для неё: напечатанное — подставное.
Не нашлась кнопка — запись не сработала: дальше она думает сама, а после двух неудач запись забывается.
Каждый шаг повтора идёт через ту же охрану (пароли никогда, «купить / отправить» — только после «да»).
Хранится в data/learned.json."""
import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import guard
from eyes import Element
from intents import norm

MAX_STEPS = 10          # длинные блуждания не запоминаем — там, скорее всего, много лишнего
MAX_ITEMS = 60
FIND_WAIT = 4.0         # столько ждём, пока нужная кнопка появится на экране
PAUSE = 0.6
Q = "{q}"


def _fixed_ok(template: str) -> bool:
    """«включи {q}» — слишком общее (подойдёт к чему угодно); нужно хотя бы 2 своих слова."""
    rest = template.replace(Q, " ").split()
    return len(rest) >= 2 and len("".join(rest)) >= 8


def make_entry(goal: str, trace: list[dict]) -> tuple[str, dict] | None:
    """(ключ, запись) или None, если запоминать нечего / ненадёжно."""
    if not trace or len(trace) > MAX_STEPS:
        return None
    g = norm(goal)
    if not g:
        return None
    for s in trace:
        if s["do"] in ("press", "type") and (not s.get("label") or s["label"].startswith("точка ")):
            return None                     # нажала по координатам (через Google) — повторить нельзя
    # «открыть» только настоящее (ссылка, знакомый сайт или программа) — иначе в повторе откроется поиск Google
    import actions
    trace = [s for s in trace if s["do"] != "open" or actions.known_target(s.get("arg", ""))
             or re.match(r"https?://|[\w-]+\.[a-z]{2,}", s.get("arg", ""))]
    if not trace:
        return None
    q = next((norm(s["text"]) for s in trace if s["do"] == "type" and len(norm(s.get("text", ""))) >= 2
              and norm(s["text"]) in g), None)
    key = g
    steps = [dict(s) for s in trace]
    if q and _fixed_ok(g.replace(q, Q, 1)):
        key = g.replace(q, Q, 1)
        for s in steps:
            if s["do"] == "type" and norm(s["text"]) == q:
                s["text"] = Q
            if s.get("label") and q in norm(s["label"]):
                s["label"] = norm(s["label"]).replace(q, Q)
    return key, {"goal": goal, "steps": steps, "uses": 0, "fails": 0, "t": int(time.time())}


class Learned:
    def __init__(self, path: Path):
        self.path = Path(path)
        try:
            self.items = json.loads(self.path.read_text("utf-8"))
        except Exception:
            self.items = {}

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), "utf-8")

    def record(self, goal: str, trace: list[dict]) -> str | None:
        e = make_entry(goal, trace)
        if e is None:
            return None
        key, entry = e
        old = self.items.get(key)
        if old:
            entry["uses"] = old.get("uses", 0)
        self.items[key] = entry
        if len(self.items) > MAX_ITEMS:          # самое старое и редкое — забываем
            worst = min(self.items, key=lambda k: (self.items[k].get("uses", 0), self.items[k].get("t", 0)))
            self.items.pop(worst, None)
        self._write()
        return key

    def find(self, goal: str) -> tuple[str, str | None] | None:
        """(ключ, что подставить) — если такую просьбу она уже умеет."""
        g = norm(goal)
        if not g or not self.items:
            return None
        if g in self.items:
            return g, None
        for key in self.items:
            if Q in key:
                a, _, b = key.partition(Q)
                m = re.fullmatch(re.escape(a) + r"(.+?)" + re.escape(b), g)
                if m and m.group(1).strip():
                    return key, m.group(1).strip()
        best, score = None, 0.0
        for key in self.items:
            if Q not in key:
                r = SequenceMatcher(None, g, key).ratio()
                if r > score:
                    best, score = key, r
        return (best, None) if score >= 0.93 else None

    def done(self, key: str, ok: bool) -> None:
        e = self.items.get(key)
        if not e:
            return
        if ok:
            e["uses"] = e.get("uses", 0) + 1
            e["fails"] = 0
        else:
            e["fails"] = e.get("fails", 0) + 1
            if e["fails"] >= 2:
                self.items.pop(key, None)
                print(f"[учусь] забыла «{key}» — дважды не сработало")
        self._write()

    def forget_all(self) -> int:
        n = len(self.items)
        self.items = {}
        self._write()
        return n


# --- повтор по записи ---
def _match_label(want: str, role: str, elements: list) -> Element | None:
    w = norm(want)
    best, score = None, 0.0
    for e in elements:
        lab = norm(e.label)
        if not lab:
            continue
        r = 1.0 if lab == w else SequenceMatcher(None, lab, w).ratio()
        if r == 1.0 and e.role == role:
            return e
        if r > score:
            best, score = e, r
    return best if score >= 0.85 else None


def _find(eyes, want: str, role: str, stop, clock, sleep):
    end = clock() + FIND_WAIT
    while True:
        snap = eyes.snapshot()
        guard.check_app(snap.app, snap.bundle_id)
        el = _match_label(want, role, snap.elements)
        if el is None and len(snap.elements) < 5:
            n = len(snap.elements)
            ocr = [Element(n + i + 1, "TEXT", t, f) for i, (t, f) in enumerate(eyes.read_text()[:60])]
            el = _match_label(want, role, ocr)
        if el is not None or clock() >= end or stop.is_set():
            return snap, el
        sleep(0.4)


def _confirmed(ask_yes, stop, fn, *a, **k):
    try:
        return fn(*a, **k)
    except guard.NeedYes as q:
        if stop.is_set() or not ask_yes(q.question):
            return None
        return fn(*a, confirmed=True, **k)


def replay(entry: dict, q: str | None, eyes, hands, ask_yes, open_fn, stop, on_step=None,
           clock=time.monotonic, sleep=time.sleep) -> bool:
    """True — все шаги сделаны. False — что-то не нашлось или он не разрешил (дальше пусть думает сама)."""
    on_step = on_step or (lambda text, el=None: None)

    def sub(s: str) -> str:
        return s.replace(Q, q) if q else s
    for s in entry["steps"]:
        if stop.is_set():
            return False
        do = s["do"]
        if do in ("press", "type"):
            snap, el = _find(eyes, sub(s["label"]), s.get("role", ""), stop, clock, sleep)
            if el is None:
                print(f"[учусь] не нашла «{sub(s['label'])}» — дальше сама")
                return False
            if do == "press":
                on_step(f"нажимаю «{el.label}»", el)
                if _confirmed(ask_yes, stop, hands.press, el, snap.app, snap.bundle_id, mouse=el.ref is None) is None:
                    return False
            else:
                on_step(f"печатаю «{sub(s['text'])}»", el)
                hands.type_text(el, sub(s["text"]), snap.app, snap.bundle_id)
        elif do == "key":
            if _confirmed(ask_yes, stop, hands.key, s["name"]) is None:
                return False
        elif do == "scroll":
            hands.scroll(s.get("arg", "вниз"))
        elif do == "open" and open_fn:
            on_step(f"открываю {sub(s['arg'])}")
            open_fn(sub(s["arg"]))
            sleep(1.5)
        sleep(PAUSE)
    return True
