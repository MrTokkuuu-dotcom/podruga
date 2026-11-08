"""Долгая память. Факты лежат в memory.md по разделам, с датой:
    - [2026-11-02] [самочувствие] кашляет, пьёт тёплый чай
Разделы: о нём, любит, люди — помнит всегда; планы — 3 недели; самочувствие — 5 дней
(чтобы спросить «как ты?»); разное — 2 недели. Когда постоянных фактов много, она раз в день
сама сжимает их (убирает повторы и устаревшее). Каждый день — резервная копия на 30 дней."""
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

CATS = {"о нём": None, "любит": None, "люди": None,
        "планы": 21, "самочувствие": 5, "разное": 14}      # None = хранить всегда
PERMANENT = [c for c, d in CATS.items() if d is None]
LINE = re.compile(r"^- \[(\d{4}-\d{2}-\d{2})\](?: \[([^\]]+)\])? (.+)$")

SUMMARY_PROMPT = (
    "Ниже разговор с {user}. Выпиши от 0 до 5 коротких фактов, которые стоит помнить дальше. "
    "Каждый факт с новой строки в виде: - [раздел] факт\n"
    "Разделы: [о нём] — постоянное (работа, учёба, где живёт, цели); [любит] — что нравится и не "
    "нравится; [люди] — о близких и друзьях; [планы] — что собирается сделать; [самочувствие] — "
    "здоровье и настроение сейчас; [разное] — остальное.\n"
    "Только то, что он сам сказал, без догадок. Не повторяй то, что уже есть в памяти:\n{known}\n"
    "Если запоминать нечего — напиши НЕТ.\n\nРазговор:\n{transcript}"
)

CONSOLIDATE_PROMPT = (
    "Это постоянная память о {user}. Сожми её: объедини повторы, убери устаревшее (если факты "
    "противоречат — оставь более новый), не выдумывай нового. Оставь не больше 25 строк "
    "в том же формате: - [дата] [раздел] факт\n\n{facts}"
)


def _parse(line: str):
    m = LINE.match(line.strip())
    if not m:
        return None
    d, cat, text = m.groups()
    cat = (cat or "разное").strip().lower()
    return {"date": d, "cat": cat if cat in CATS else "разное", "text": text.strip()}


class Memory:
    def __init__(self, data_dir: Path, keep_days: int = 30):
        self.file = Path(data_dir) / "memory.md"
        self.backup_dir = Path(data_dir) / "backups"
        self.keep_days = keep_days
        self.last_consolidated = None

    def facts(self) -> list[dict]:
        if not self.file.exists():
            return []
        out = []
        for line in self.file.read_text(encoding="utf-8").splitlines():
            f = _parse(line)
            if f:
                out.append(f)
        return out

    def read(self) -> str:
        """Текст для подсказки: постоянное целиком, временное — только свежее."""
        today = date.today()
        perm, recent = [], []
        for f in self.facts():
            keep = CATS[f["cat"]]
            if keep is None:
                perm.append(f"- [{f['cat']}] {f['text']}")
            elif (today - date.fromisoformat(f["date"])).days <= keep:
                when = _ago(date.fromisoformat(f["date"]), today)
                recent.append(f"- {when} [{f['cat']}] {f['text']}")
        parts = []
        if perm:
            parts += ["Постоянное:", *perm]
        if recent:
            parts += ["", "Недавнее (можно иногда мягко спросить, как оно сейчас — но не каждый раз):",
                      *recent]
        return "\n".join(parts)

    def to_ask(self) -> tuple[str, str] | None:
        """О чём стоит самой спросить: свежие планы и самочувствие (вчера–3 дня назад, сегодняшнее —
        если прошло полдня), о которых она ещё не спрашивала. → (факт, «вчера»/«позавчера»…) или None."""
        import json
        asked_file = self.file.parent / "asked.json"
        try:
            asked = set(json.loads(asked_file.read_text(encoding="utf-8")))
        except (FileNotFoundError, ValueError):
            asked = set()
        today = date.today()
        best = None
        for f in self.facts():
            if f["cat"] not in ("планы", "самочувствие") or f["text"] in asked:
                continue
            days = (today - date.fromisoformat(f["date"])).days
            if 1 <= days <= 3 and (best is None or days < best[0]):
                best = (days, f)
        if not best:
            return None
        return best[1]["text"], _ago(date.fromisoformat(best[1]["date"]), today)

    def mark_asked(self, text: str) -> None:
        import json
        asked_file = self.file.parent / "asked.json"
        try:
            asked = json.loads(asked_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            asked = []
        asked = (asked + [text])[-200:]
        asked_file.write_text(json.dumps(asked, ensure_ascii=False), encoding="utf-8")

    def add_facts(self, facts: list[str]) -> None:
        if not facts:
            return
        stamp = date.today().isoformat()
        with open(self.file, "a", encoding="utf-8") as fh:
            for fact in facts:
                m = re.match(r"\[([^\]]+)\]\s*(.+)", fact)
                cat, text = (m.group(1).strip().lower(), m.group(2).strip()) if m else ("разное", fact)
                if cat not in CATS:
                    cat = "разное"
                fh.write(f"- [{stamp}] [{cat}] {text}\n")

    def consolidate(self, brain, user: str) -> bool:
        """Раз в день, если постоянных фактов больше 40: сжать их с помощью мозга."""
        if self.last_consolidated == date.today():
            return False
        all_f = self.facts()
        perm = [f for f in all_f if CATS[f["cat"]] is None]
        if len(perm) <= 40:
            return False
        self.last_consolidated = date.today()
        text = "\n".join(f"- [{f['date']}] [{f['cat']}] {f['text']}" for f in perm)
        reply = brain.chat([{"role": "user", "content": CONSOLIDATE_PROMPT.format(user=user, facts=text)}],
                           options={"temperature": 0.1})
        new_perm = [_parse(l) for l in reply.splitlines()]
        new_perm = [f for f in new_perm if f and CATS.get(f["cat"], 0) is None]
        if not (5 <= len(new_perm) <= 30):
            return False                      # ответ странный — ничего не трогаем
        self.backup_daily(force=True)
        rest = [f for f in all_f if CATS[f["cat"]] is not None]
        lines = [f"- [{f['date']}] [{f['cat']}] {f['text']}" for f in new_perm + rest]
        self.file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[память] сжала постоянное: {len(perm)} → {len(new_perm)}")
        return True

    def migrate(self, brain) -> bool:
        """Старые записи без раздела (из первой версии) — один раз разложить по разделам."""
        if not self.file.exists():
            return False
        lines = self.file.read_text(encoding="utf-8").splitlines()
        old = [l for l in lines if LINE.match(l.strip()) and not LINE.match(l.strip()).group(2)]
        if not old:
            return False
        prompt = ("Проставь каждому факту раздел: о нём, любит, люди, планы, самочувствие или разное. "
                  "Верни те же строки в формате: - [дата] [раздел] факт. Ничего не добавляй.\n\n"
                  + "\n".join(old))
        reply = brain.chat([{"role": "user", "content": prompt}], options={"temperature": 0.1})
        fixed = [_parse(l) for l in reply.splitlines()]
        fixed = [f for f in fixed if f]
        if len(fixed) < len(old) * 0.7:
            return False
        self.backup_daily(force=True)
        keep = [l for l in lines if l not in old]
        keep += [f"- [{f['date']}] [{f['cat']}] {f['text']}" for f in fixed]
        self.file.write_text("\n".join(keep) + "\n", encoding="utf-8")
        print(f"[память] разложила по разделам {len(fixed)} старых записей")
        return True

    def backup_daily(self, force: bool = False) -> None:
        if not self.file.exists():
            return
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        today = self.backup_dir / f"memory-{date.today().isoformat()}.md"
        if force or not today.exists():
            shutil.copy2(self.file, today)
        border = date.today() - timedelta(days=self.keep_days)
        for old in self.backup_dir.glob("memory-*.md"):
            m = re.match(r"memory-(\d{4}-\d{2}-\d{2})\.md$", old.name)
            if m and date.fromisoformat(m.group(1)) < border:
                old.unlink()


def _ago(d: date, today: date) -> str:
    n = (today - d).days
    return "сегодня" if n == 0 else "вчера" if n == 1 else f"{n} дн. назад"


def parse_facts(text: str) -> list[str]:
    if text.strip().upper().startswith("НЕТ"):
        return []
    facts = [line.strip()[2:].strip() for line in text.splitlines()
             if line.strip().startswith("- ")]
    return [f for f in facts if f][:5]


def extract_facts(brain, transcript: str, user: str, known: str = "") -> list[str]:
    prompt = SUMMARY_PROMPT.format(user=user, transcript=transcript, known=known or "(пусто)")
    reply = brain.chat([{"role": "user", "content": prompt}], options={"temperature": 0.2})
    return parse_facts(reply)
