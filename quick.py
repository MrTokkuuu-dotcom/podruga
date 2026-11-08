"""Быстрые ответы без Google. Короткие простые фразы («привет», «как дела», «который час»,
«открой ютуб», «поставь таймер на пять минут») распознаются прямо на Mac и получают готовый
ответ из replies.txt за доли секунды. Всё сложное по-прежнему уходит в Gemini.

Формат replies.txt (свои ответы можно дописать в ~/Podruga/data/replies_my.txt — тот же формат):
  ## название            — новый раздел
  @всегда                — раздел работает, даже если она только что задала вопрос
  @ответ                 — это ответ на её вопрос («нормально», «хорошо») — тоже можно сразу
  ? фраза                — как он может сказать (слова через пробел; {n} — число, {что} — остаток)
  ! КОМАНДА {что}        — что выполнить (как у Gemini: ОТКРЫТЬ, МУЗЫКА, ГРОМКОСТЬ, ТАЙМЕР)
  {эмоция} текст         — вариант ответа; [утро]/[день]/[вечер]/[ночь] в начале — только в это время
В ответах можно писать {user}, {name}, {time}, {date}, {weekday}, {daypart}, {n}, {что}."""
import random
import re
from collections import deque
from datetime import datetime
from pathlib import Path

FILLER = {"ну", "слушай", "а", "вот", "да", "ага", "угу", "ой", "так", "эй", "это", "же", "ладно", "короче", "кстати",
          "блин", "ой", "о", "подруга", "подружка", "солнышко", "милая", "дорогая", "пожалуйста",
          "ты", "мне", "мол", "типа", "просто", "уже", "вообще", "давай-ка", "ну-ка"}
FILLER |= {"кстати", "короче", "бля", "блин", "блядь", "сука", "епта", "млин", "слышь", "значит", "получается",
           "походу", "типо", "сейчас", "щас", "теперь", "тогда", "вобщем", "в общем", "ну-ка", "аня", "анечка", "анют", "анюта", "солнце", "зай", "зая"}
KEEP_FILLER = {"ты", "мне"}          # убираем, только если без них фраза совпала
NUM = {"ноль": 0, "один": 1, "одну": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4,
       "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
       "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
       "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
       "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
       "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90, "сто": 100,
       "полчаса": 30, "полминуты": 1, "минуту": 1, "часик": 60, "час": 60}
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
          "октября", "ноября", "декабря"]
EMO_RU = {"радость": "joy", "нежность": "tender", "смущение": "shy", "удивление": "surprise",
          "грусть": "sad", "задумчивость": "think", "спокойствие": "calm"}


def norm(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s\-]", " ", text)
    return " ".join(text.split())


def daypart(t: datetime) -> str:
    h = t.hour
    return "утро" if 5 <= h < 12 else "день" if 12 <= h < 18 else "вечер" if 18 <= h < 23 else "ночь"


def words_to_number(ws: list[str]) -> int | None:
    if not ws:
        return None
    if len(ws) == 1 and ws[0].isdigit():
        return int(ws[0])
    total, ok = 0, False
    for w in ws:
        if w.isdigit():
            total += int(w); ok = True
        elif w in NUM:
            total += NUM[w]; ok = True
        else:
            return None
    return total if ok else None


class Section:
    def __init__(self, name: str):
        self.name = name
        self.triggers: list[list[str]] = []
        self.commands: list[str] = []
        self.replies: list[tuple[str | None, str, str]] = []   # (время суток, эмоция, текст)
        self.always = False
        self.answer = False
        self.service = False
        self.recent: deque = deque(maxlen=8)


def load(paths: list[Path]) -> list[Section]:
    sections, cur = [], None
    for path in paths:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") and not line.startswith("##"):
                continue
            if line.startswith("##"):
                name = line[2:].strip()
                cur = next((x for x in sections if x.name == name), None)   # одноимённые — объединяем
                if cur is None:
                    cur = Section(name)
                    sections.append(cur)
            elif cur is None:
                continue
            elif line == "@всегда":
                cur.always = True
            elif line == "@ответ":
                cur.answer = True
            elif line == "@служебное":
                cur.service = True
            elif line.startswith("?"):
                t = line[1:].replace("{n}", " qqnum ").replace("{что}", " qqrest ").replace("*", "qqstar")
                t = norm(t).replace("qqnum", "{n}").replace("qqrest", "{что}").replace("qqstar", "*")
                cur.triggers.append(t.split())
            elif line.startswith("!"):
                cur.commands.append(line[1:].strip())
            else:
                part = None
                m = re.match(r"\[(утро|день|вечер|ночь)\]\s*", line)
                if m:
                    part, line = m.group(1), line[m.end():]
                emo = "calm"
                m = re.match(r"\{(\w+)\}\s*", line)
                if m and m.group(1) in EMO_RU:
                    emo, line = EMO_RU[m.group(1)], line[m.end():]
                cur.replies.append((part, emo, line))
    return [s for s in sections if s.service or (s.triggers and (s.replies or s.commands))]


def _match_trigger(trig: list[str], ws: list[str], start: int):
    """Совпадает ли фраза-шаблон с куском ws, начиная с start. Возвращает (конец, захваты)."""
    caps, i = {}, start
    for k, t in enumerate(trig):
        if t == "{что}":
            rest = ws[i:]
            if not rest:
                return None
            caps["что"] = " ".join(rest)
            return len(ws), caps
        if t == "{n}":
            j = i
            while j < len(ws) and (ws[j].isdigit() or ws[j] in NUM) and ws[j] not in ("минуту", "час"):
                j += 1
            n = words_to_number(ws[i:j])
            if n is None:
                return None
            caps["n"] = n
            i = j
            continue
        if i >= len(ws):
            return None
        if t.endswith("*"):
            if not ws[i].startswith(t[:-1]):
                return None
        elif ws[i] != t:
            return None
        i += 1
    return i, caps


class QuickReplies:
    def __init__(self, app_dir: Path, data_dir: Path):
        # replies.txt + replies_*.txt рядом с программой (большие наборы), в конце — свои из data
        extra = sorted(p for p in Path(app_dir).glob("replies_*.txt"))
        self.paths = [Path(app_dir) / "replies.txt", *extra, Path(data_dir) / "replies_my.txt"]
        self.reload()

    def reload(self):
        self.sections = load(self.paths)
        self.vocab = sorted({w.rstrip("*") for s in self.sections for t in s.triggers for w in t
                             if not w.startswith("{") and len(w) >= 4 and w not in FILLER})
        n = sum(len(s.replies) for s in self.sections)
        print(f"[быстро] готовых ответов: {n} в {len(self.sections)} разделах")

    # разбить фразу на 1–3 известных куска («привет как дела» = привет + как дела)
    def _segment(self, ws: list[str]):
        best = None

        def walk(i, acc):
            nonlocal best
            if len(acc) > 3:
                return
            if i == len(ws):
                if best is None or len(acc) < len(best):
                    best = list(acc)
                return
            for s in self.sections:
                if s.service:
                    continue
                for trig in s.triggers:
                    r = _match_trigger(trig, ws, i)
                    if r:
                        walk(r[0], acc + [(s, r[1])])
        walk(0, [])
        return best

    def match(self, text: str, after_question: bool = False):
        """→ (ответ, эмоция, [команды]) или None, если пусть думает Gemini."""
        ws = norm(text).split()
        if not ws or len(ws) > 9:
            return None
        base = [ws, [w for w in ws if w not in FILLER - KEEP_FILLER], [w for w in ws if w not in FILLER]]
        cands = []
        for c in base + [self._fix(c) for c in base]:   # + Whisper написал слово чуть иначе — подбираем похожее
            if c and c not in cands:
                cands.append(c)
        seg = None
        for c in cands:                           # первый вариант, который подходит по ходу разговора
            sg = self._segment(c)
            if not sg:
                continue
            if after_question and len(c) < 2 and not all(s.always or s.answer for s, _ in sg):
                continue                          # она что-то спросила, а в ответ одно слово не по теме — пусть подумает Gemini
            if not after_question and any(s.answer and not s.always for s, _ in sg):
                continue                          # «нормально» без её вопроса — непонятно к чему
            seg = sg
            break
        if not seg:
            return None
        t = datetime.now()
        texts, emo, cmds = [], "calm", []
        for k, (s, caps) in enumerate(seg):
            ctx = {"n": caps.get("n", ""), "что": caps.get("что", "")}
            cmds += [c.replace("{n}", str(ctx["n"])).replace("{что}", ctx["что"]) for c in s.commands]
            if s.replies:
                text_, e = self._pick(s, t, no_question=k < len(seg) - 1)   # вопрос — только в конце
                texts.append((text_, ctx))
                if emo == "calm":
                    emo = e
        return texts, emo, cmds

    def _fix(self, ws: list[str]) -> list[str]:
        from difflib import get_close_matches
        out = []
        for w in ws:
            if len(w) >= 4 and not w.isdigit() and w not in self.vocab and w not in NUM:
                m = get_close_matches(w, self.vocab, n=1, cutoff=0.82)
                w = m[0] if m else w
            out.append(w)
        return out

    def _pick(self, s: Section, t: datetime, no_question: bool = False):
        dp = daypart(t)
        ok = [i for i, (p, _, _) in enumerate(s.replies) if p in (None, dp)]
        if no_question:
            ok = [i for i in ok if "?" not in s.replies[i][2]] or ok
        fresh = [i for i in ok if i not in s.recent] or ok
        i = random.choice(fresh)
        s.recent.append(i)
        return s.replies[i][2], s.replies[i][1]

    def service(self, name: str):
        """Фраза из служебного раздела (например, «думаю» — пока ждём Google)."""
        s = next((x for x in self.sections if x.service and x.name == name and x.replies), None)
        return self._pick(s, datetime.now()) if s else None

    # --- самообучение: частые простые фразы, на которые всё равно ходили в Google ---
    LEARN_BLOCK = ("какой", "какая", "какое", "какие", "сколько", "когда", "где", "почему", "зачем",
                   "погода", "новости", "курс", "переведи", "найди", "посмотри", "глянь", "напомни",
                   "таймер", "открой", "включи", "сегодня", "завтра", "вчера")

    def learn(self, path: Path, heard: str, reply: str, emo: str, after_question: bool) -> str | None:
        """Запомнить пару «фраза → ответ Gemini». Когда фраза встретилась 3 раза с разными ответами —
        добавляем её в replies_my.txt. Возвращает фразу, если что-то выучили."""
        import json
        ws = norm(heard).split()
        if after_question or not 1 <= len(ws) <= 4 or any(w.isdigit() for w in ws):
            return None
        if any(w.startswith(b) for w in ws for b in self.LEARN_BLOCK):
            return None
        if not reply or len(reply.split()) > 25 or "<<" in reply:
            return None
        if "?" in reply and len(reply.split()) > 6:
            return None                       # длинный вопрос обычно про что-то конкретное из памяти
        key = " ".join(ws)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            data = {}
        e = data.setdefault(key, {"count": 0, "replies": []})
        e["count"] += 1
        if reply not in [r for _, r in e["replies"]]:
            e["replies"] = (e["replies"] + [[emo, reply]])[-8:]
        learned = None
        if e["count"] >= 3 and len(e["replies"]) >= 3 and not e.get("done"):
            ru = {v: k for k, v in EMO_RU.items()}
            block = [f"\n## выучено: {key}", f"? {key}"] + [f"{{{ru.get(em, 'спокойствие')}}} {r}" for em, r in e["replies"]]
            mine = Path(self.paths[1])
            mine.parent.mkdir(parents=True, exist_ok=True)
            with open(mine, "a", encoding="utf-8") as f:
                f.write("\n".join(block) + "\n")
            e["done"] = True
            learned = key
            self.reload()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return learned

    @staticmethod
    def fill(text: str, ctx: dict, user: str, name: str) -> str:
        t = datetime.now()
        vals = {"user": user, "name": name, "time": t.strftime("%H:%M"),
                "date": f"{t.day} {MONTHS[t.month - 1]}", "weekday": WEEKDAYS[t.weekday()],
                "daypart": daypart(t), "n": str(ctx.get("n", "")), "что": ctx.get("что", "")}
        return re.sub(r"\{(\w+)\}", lambda m: vals.get(m.group(1), m.group(0)), text)
