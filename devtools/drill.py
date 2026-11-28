"""Учебный прогон: сотни фраз через тот же путь, что голос и переписка (Companion.route), но тихо.
Ничего не делает по-настоящему: команды, Mac, руки и задачи подменены записью «что бы она сделала»,
голос выключен, данные — во временной папке (не ~/Podruga/data), ключ Google не используется.

Запуск:  ~/Podruga/venv/bin/python devtools/drill.py                 # только маршрут (быстро, без мозга)
         ~/Podruga/venv/bin/python devtools/drill.py --brain         # + свой мозг на фразах, которые уходят ему
         ... --out drill_report  (пишет drill_report.json и drill_report.md), --only музыка (раздел), --limit 50

Файл фраз (devtools/drill_phrases.txt), строка:  ожидание | фраза
  ожидание — путь[:команда], несколько вариантов через «/»:  device:МУЗЫКА pause,  brain:СДЕЛАТЬ,  quick/brain,
  brain:-  (мозг, без команд),  quick:-  (готовый ответ, без команд).
  Пути: sleep body intercept habit lessons modes mac task learned repeat device quick brain.
  Команды: то, что ушло бы в handle_commands («ОТКРЫТЬ ютуб», «МУЗЫКА play», «ТАЙМЕР 5 | таймер», «СДЕЛАТЬ …»,
  «НАПОМНИТЬ …», «ПОИСК …»), а ещё «MAC quit Telegram», «MODE рабочий режим», «BODY sit», «REDO …».
  Сравнение команды — по началу строки, без учёта регистра.
  «# Раздел» — заголовок раздела. Служебные строки:  @reset (забыть разговор),  @task (идёт задача на экране),
  @habit фраза (она только что предложила привычку),  @acted (она только что что-то сделала),
  @her текст (её прошлая реплика)."""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("PODRUGA_HOME", str(Path.home() / "Podruga"))   # модели — оттуда, данные — во временной папке

# main.py при импорте проверяет обновления с GitHub — стенду это не нужно
_boot = types.ModuleType("bootstrap")
_boot.check_update = lambda: None
_boot.ensure_deps = lambda: None
sys.modules["bootstrap"] = _boot

RUNNING_APPS = ["Telegram", "Google Chrome", "Safari", "KakaoTalk", "Discord", "Finder", "Notes", "CapCut", "Steam"]
PATHS = {"sleep", "body", "intercept", "habit", "lessons", "modes", "mac", "task", "learned", "repeat", "device",
         "quick", "brain"}


def parse_phrases(path: Path):
    """→ список {section, expect, text} и служебных {directive, arg, section}."""
    items, section = [], ""
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            section = line.lstrip("#").strip()
            continue
        if line.startswith("@"):
            d, _, arg = line[1:].partition(" ")
            items.append({"directive": d, "arg": arg.strip(), "section": section, "line": n})
            continue
        exp, sep, text = line.partition("|")
        if not sep:
            raise SystemExit(f"{path.name}:{n}: нет «|»: {line}")
        alts = []
        for a in exp.split("/"):
            p, _, c = a.strip().partition(":")
            if p not in PATHS:
                raise SystemExit(f"{path.name}:{n}: неизвестный путь «{p}»")
            alts.append((p, c.strip()))
        items.append({"section": section, "expect": exp.strip(), "alts": alts, "text": text.strip(), "line": n})
    return items


def matches(alts, path: str, acts: list[str], brain: bool = True) -> bool:
    for p, c in alts:
        if p != path:
            continue
        if not c or (p == "brain" and not brain):      # без мозга команды мозга не проверить
            return True
        if c == "-" and not acts:
            return True
        if c != "-" and any(a.lower().startswith(c.lower()) for a in acts):
            return True
    return False


class Recorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.acts, self.lines, self.first = [], [], None
        self.t0 = time.monotonic()

    def act(self, s: str):
        s = " ".join(str(s).split())
        with self.lock:
            if s not in self.acts:
                self.acts.append(s)

    def line(self, s: str):
        with self.lock:
            if self.first is None:
                self.first = time.monotonic() - self.t0
            self.lines.append(s)


class _Speaker:
    def __init__(self, rec):
        self.rec = rec

    def speak(self, text, emotion="calm"):
        self.rec.line(text)

    def wait_done(self):
        pass

    def stop(self):
        pass


class _Walker:
    def __init__(self, rec):
        self.rec = rec

    def command(self, arg):
        self.rec.act(f"ГУЛЯТЬ {arg}")

    def __getattr__(self, name):            # stop, wake, begin_sleep … — ничего не делать
        return lambda *a, **k: False


def build(brain: bool, keep_dir: Path | None = None):
    import config
    import actions
    import mac
    import main
    cfg = config.load_config()
    os.environ.pop("GEMINI_API_KEY", None)        # только свой мозг: бесплатно и без сети
    tmp = keep_dir or Path(tempfile.mkdtemp(prefix="podruga_drill_"))
    tmp.mkdir(parents=True, exist_ok=True)
    cfg["_data_dir"] = tmp
    cfg.setdefault("quick", {})["followup"] = False   # «продолжение от мозга» после заготовки — не про маршрут
    if not brain:
        cfg["brain"]["engine"] = "local"
    rec = Recorder()

    # что бы она сделала на Mac — только запись
    mac.running_apps = lambda: list(RUNNING_APPS)
    mac._sound = lambda: False

    def fake_run(kind, arg, sound=None):
        rec.act(f"{kind.upper()} {arg}")
        return "ok"
    actions.run = fake_run

    comp = main.Companion(cfg, text_mode=True)
    from quick import QuickReplies
    import avatars
    comp.quick = QuickReplies(main.ROOT, tmp)
    comp.quick.girl = avatars.current_girl(cfg)
    comp.quick.learn = lambda *a, **k: None          # не учиться на ходу: прогон должен быть повторяемым
    comp.speaker = _Speaker(rec)
    comp.walker = _Walker(rec)
    comp.screenshot = lambda: None
    comp.ui.move_to_screen = lambda arg: (rec.act(f"MAC screen {arg}"), True)[1]

    orig_handle = comp.handle_commands

    def handle(cmds):
        for c in cmds:
            rec.act(c.strip())
        orig_handle(cmds)
    comp.handle_commands = handle
    comp._do_action = lambda kind, arg, sound=None: None        # уже записано в handle
    comp._do_search = lambda q: None
    comp._mac_do = lambda kind, arg: rec.act(f"MAC {kind} {arg}".strip())
    comp._run_mode = lambda name, steps: rec.act(f"MODE {name}")
    comp._redo = lambda text: rec.act(f"REDO {text}")
    comp.initiative.add_from_command = lambda c: None
    comp.tasks.start = lambda goal, fn=None, said=None: rec.act(f"СДЕЛАТЬ {goal}")
    comp.go_sleep = lambda say_goodnight=True: rec.act("СОН")
    comp._sync_local_orig = comp._sync_local

    if brain:
        comp._start_local()
        loc = comp.local
        if loc is None:
            print("⚠ свой мозг на этом Mac не включается — прогон без мозга")
        else:
            print("…гружу свой мозг (Gemma)…", flush=True)
            loc.preload()
            if not loc.ready.wait(240):
                print("⚠ мозг не загрузился за 4 мин — прогон без мозга")
    comp.ready.set()
    return comp, rec, tmp


def run_one(comp, rec, text: str) -> tuple[str, float]:
    """Тот же порядок, что в main.on_phrase для расшифрованной фразы (плюс «посмотри» из переписки)."""
    import intents
    from tts import VoiceRouter
    from wake import LOOK_PHRASES, _norm
    comp._phrase_lang = VoiceRouter.script_of(text)
    if comp.local is not None:                     # мозг отвечает со случайностью (0,8): одно «зерно» на фразу
        try:
            import zlib
            import mlx.core as mx
            mx.random.seed(zlib.crc32(text.encode()))
        except Exception:
            pass
    look = any(p in _norm(text) for p in LOOK_PHRASES)
    t0 = time.monotonic()
    rec.t0 = t0
    if comp.tasks.intercept(text):
        path = "intercept"
    elif comp.habit_answer(text, spoken=False):
        path = "habit"
    elif intents.is_sleep(text):
        path = "sleep"
        rec.act("СОН")
    elif intents.body_command(text):
        path = "body"
        rec.act(f"BODY {intents.body_command(text)}")
    else:
        comp.last_parser = None
        path = comp.route(text, look, spoken=False) if hasattr(comp, "route") else _route_v34(comp, text, look)
        if path == "brain" and comp.last_parser is not None and comp.last_parser.skip:
            rec.act("МОЛЧУ")
    secs = time.monotonic() - t0
    for th in threading.enumerate():               # фоновые записи (handle_commands → поток) — дождаться
        if th is not threading.current_thread() and th.name in ("mac", "mode", "redo", "habit") or \
                th.name.startswith("Thread-"):
            th.join(0.5)
    return path, secs


def _route_v34(comp, text: str, look: bool) -> str:
    """Тот же порядок для старых версий (до v35 в main.py не было route) — чтобы сравнить «до/после»."""
    if comp.lessons_now(text, spoken=False):
        return "lessons"
    text = comp.rewrite(text)
    if comp.modes_now(text, spoken=False):
        return "modes"
    if comp.mac_now(text, spoken=False, look=look):
        return "mac"
    if not look:
        for name, fn in (("task", comp.task_now), ("learned", comp.learned_now), ("repeat", comp.repeat_now),
                         ("device", comp.device_now)):
            if fn(text, spoken=False):
                return name
        if comp.quick_answer(text=text):
            return "quick"
    comp.respond(text=text, image=None)
    return "brain"


def directive(comp, d: str, arg: str):
    if d == "reset":
        comp.history.clear()
        comp._acted = 0.0
        comp._habit_q = None
        comp.tasks.running = False
        comp.set_lang("ru")
        comp._repeat_mode = False
    elif d == "task":
        comp.tasks.running = True
    elif d == "habit":
        comp._habit_q = (arg.lower(), arg, time.monotonic())
    elif d == "acted":
        comp._acted = time.monotonic()
    elif d == "her":
        comp.history.append({"role": "model", "text": arg})
    else:
        raise SystemExit(f"неизвестная служебная строка @{d}")


def report_md(results, title: str) -> str:
    total = len(results)
    ok = sum(r["ok"] for r in results)
    out = [f"# {title}", "", f"Всего {total}, верно {ok} ({100 * ok / max(1, total):.0f}%), ошибок {total - ok}.", ""]
    out += ["| Раздел | верно | всего |", "|---|---|---|"]
    secs = {}
    for r in results:
        s = secs.setdefault(r["section"], [0, 0])
        s[0] += r["ok"]
        s[1] += 1
    out += [f"| {k} | {v[0]} | {v[1]} |" for k, v in secs.items()]
    paths = {}
    for r in results:
        paths.setdefault(r["path"], []).append(r["secs"])
    out += ["", "| Путь | фраз | среднее, с | худшее, с |", "|---|---|---|---|"]
    out += [f"| {k} | {len(v)} | {sum(v) / len(v):.2f} | {max(v):.2f} |" for k, v in sorted(paths.items())]
    bad = [r for r in results if not r["ok"]]
    if bad:
        out += ["", "## Ошибки", "", "| # | фраза | ждали | вышло | команды | ответ |", "|---|---|---|---|---|---|"]
        for r in bad:
            out.append(f"| {r['line']} | {r['text']} | {r['expect']} | {r['path']} | {'; '.join(r['acts'])[:80]} | "
                       f"{r['reply'][:80]} |".replace("\n", " "))
    slow = [r for r in results if (r["path"] != "brain" and r["secs"] > 0.5) or r["secs"] > 8]
    if slow:
        out += ["", "## Медленно (сразу > 0,5 с, мозг > 8 с)", ""]
        out += [f"- {r['secs']:.2f} с — {r['path']} — «{r['text']}»" for r in slow]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phrases", nargs="?", default=str(REPO / "devtools" / "drill_phrases.txt"))
    ap.add_argument("--brain", action="store_true", help="фразы, которые уходят мозгу, — через свой мозг")
    ap.add_argument("--out", default="", help="куда записать отчёт (без расширения): .json и .md")
    ap.add_argument("--only", default="", help="только разделы, где есть это слово")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--title", default="Учебный прогон")
    a = ap.parse_args()

    items = parse_phrases(Path(a.phrases))
    if a.only:
        items = [x for x in items if a.only.lower() in x["section"].lower()]
    import builtins
    real_print = builtins.print
    quiet = os.environ.get("DRILL_VERBOSE") != "1"
    import random
    random.seed(7)                                   # готовые ответы выбираются случайно — прогон должен повторяться
    comp, rec, tmp = build(a.brain)
    brain_on = comp.brain is not None
    results = []
    n = 0
    try:
        for it in items:
            if "directive" in it:
                directive(comp, it["directive"], it["arg"])
                continue
            n += 1
            if a.limit and n > a.limit:
                break
            rec.reset()
            if quiet:
                builtins.print = lambda *x, **k: None
            try:
                path, secs = run_one(comp, rec, it["text"])
            except Exception as e:
                path, secs = f"error: {e}", 0.0
            finally:
                builtins.print = real_print
            reply = " ".join(rec.lines)
            ok = matches(it["alts"], path, rec.acts, brain_on)
            r = {"line": it["line"], "section": it["section"], "text": it["text"], "expect": it["expect"],
                 "path": path, "acts": list(rec.acts), "reply": reply, "secs": round(secs, 3),
                 "first": round(rec.first, 3) if rec.first is not None else None, "ok": ok}
            results.append(r)
            mark = "✓" if ok else "✗"
            real_print(f"{mark} {secs:5.2f}s {path:8} {'; '.join(r['acts'])[:50]:50} «{it['text']}»"
                       + ("" if ok else f"   ← ждали {it['expect']}"), flush=True)
            comp.tasks.running = False
    finally:
        builtins.print = real_print
        shutil.rmtree(tmp, ignore_errors=True)
    ok = sum(r["ok"] for r in results)
    print(f"\nИтого: {ok}/{len(results)} верно ({100 * ok / max(1, len(results)):.0f}%)")
    if a.out:
        out = Path(a.out)
        out.with_suffix(".json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        out.with_suffix(".md").write_text(report_md(results, a.title), encoding="utf-8")
        print(f"Отчёт: {out.with_suffix('.md')}")
    sys.stdout.flush()
    os._exit(0 if ok == len(results) else 1)      # фоновые потоки мозга не ждём


if __name__ == "__main__":
    main()
