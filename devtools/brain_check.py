"""Прогон своего мозга на 16 фразах: род, команды, языки, «не мне», память.
Запуск: ~/Podruga/venv/bin/python devtools/brain_check.py   (нужна модель в ~/Podruga/models/brain/)"""
import json
import re
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from local_brain import LocalBrain  # noqa: E402
from local_prompt import stable_system  # noqa: E402
from reply_parser import ReplyParser  # noqa: E402

USER, NAME = "Дима", "Аня"
character = (REPO / "character.md").read_text(encoding="utf-8").format(name=NAME, user=USER)
girls = json.loads((REPO / "avatars.json").read_text(encoding="utf-8"))["girls"]
anya = girls[0] if isinstance(girls, list) else next(iter(girls.values()))
own = (anya.get("persona") or {}).get("character")
if own:
    character += "\n\n## Какая именно ты\n" + own
MEMORY = """- Его зовут Дима, живёт в Сеуле.
- Работает дизайнером, часто устаёт к вечеру; любит рисовать комиксы.
- Играет в шахматы с другом Петей по выходным.
- Любит острую корейскую еду, особенно рамён.
- Учит корейский, иногда просит говорить по-корейски.
- Есть кошка Муся.
- Планировал на выходных съездить в горы.
- Не любит, когда его будят рано."""
TRAITS = "- Мягкая, но с характером: можешь по-доброму пошутить.\n- В меру игривая: шутишь к месту.\n- Отвечаешь 1–2 предложениями."
FRESH = "## Сейчас\nвоскресенье, 23.11.2026 21:40"
MASC = re.compile(r"\bя\s+(понял|рад|устал|сам|готов|сделал|подумал|согласен|уверен)\b", re.I)


def cmd(p, start):
    return any(c.upper().replace(" ", "").startswith(start.upper().replace(" ", "")) for c in p.commands)


def spoken(p):
    return bool(p.reply.strip()) and not p.skip


TESTS = [  # (фраза, язык, проверка)
    ("привет, как дела?", "ru", spoken),
    ("я сегодня так устал на работе, сил нет", "ru", spoken),
    ("включи музыку", "ru", lambda p: cmd(p, "МУЗЫКА play")),
    ("открой ютуб и найди видео с котиками", "ru", lambda p: any("youtube" in c.lower() and c.upper().startswith(("ОТКРЫТЬ", "СДЕЛАТЬ")) for c in p.commands)),
    ("напомни через 10 минут выключить чайник", "ru", lambda p: cmd(p, "НАПОМНИТЬ +10")),
    ("какая завтра погода в Сеуле?", "ru", lambda p: cmd(p, "ПОИСК")),
    ("ты меня любишь?", "ru", spoken),
    ("что ты про меня помнишь?", "ru", lambda p: spoken(p) and re.search(r"Сеул|шахмат|кошк|Мус|рамён|корейск|комикс|дизайн|Пет", p.reply, re.I)),
    ("Марина, подай соль пожалуйста", "ru", lambda p: p.skip),
    ("расскажи что-нибудь смешное", "ru", spoken),
    ("я понял, что ты была права вчера", "ru", spoken),
    ("How was your day?", "en", lambda p: spoken(p) and len(re.findall(r"[A-Za-z]", p.reply)) > 2 * len(re.findall(r"[А-Яа-яЁё]", p.reply))),
    ("오늘 저녁에 뭐 먹을까?", "ko", lambda p: spoken(p) and re.search(r"[가-힣]", p.reply)),
    ("сделай погромче", "ru", lambda p: cmd(p, "ГРОМКОСТЬ +")),
    ("поставь таймер на 5 минут", "ru", lambda p: cmd(p, "ТАЙМЕР 5")),
    ("Сань, я сам сделаю", "ru", lambda p: p.skip),
]


def main():
    home = Path.home() / "Podruga"
    brain = LocalBrain(home, notify=print)
    brain.set_system(stable_system(character, TRAITS, MEMORY, USER))
    if not brain.ready.wait(600) or brain.failed:
        sys.exit("мозг не загрузился")
    brain.say_once(FRESH, "Скажи «готова».")            # прогрев кэша характера
    score, firsts = 0, []
    for text, lang, check in TESTS:
        p = ReplyParser()
        t0 = time.monotonic(); first = None; raw = ""
        for chunk in brain.stream_reply(FRESH, [], text=text, lang=lang):
            raw += chunk
            if p.feed(chunk) and first is None:
                first = time.monotonic() - t0
        p.finish()
        first = first or (time.monotonic() - t0)
        firsts.append(first)
        ok = bool(check(p)) and not MASC.search(p.reply)
        score += ok
        print(f"{'✓' if ok else '✗'} {text}  ({first:.2f} с)\n    {raw.strip()}")
    # история: длинный разговор не должен тормозить
    hist = []
    for i in range(10):
        hist += [{"role": "user", "text": f"фраза номер {i}, просто болтаем о погоде и играх"},
                 {"role": "model", "text": "{радость} Ага, интересно! Расскажи ещё."}]
    t0 = time.monotonic()
    next(iter(brain.stream_reply(FRESH, hist, text="а ты что думаешь?", lang="ru")))
    t_hist = time.monotonic() - t0
    t0 = time.monotonic()
    next(iter(brain.stream_reply(FRESH, hist[2:] + hist[:2], text="а ещё?", lang="ru")))
    t_shift = time.monotonic() - t0
    grown = hist[2:] + hist[:2] + [{"role": "user", "text": "а ещё?"}, {"role": "model", "text": "{радость} Ещё я люблю гулять."}]
    t0 = time.monotonic()
    next(iter(brain.stream_reply(FRESH, grown, text="понятно", lang="ru")))
    t_grow = time.monotonic() - t0
    # два запроса сразу (продолжение и его фраза) — по очереди, без падения
    import threading
    res = {}
    th = threading.Thread(target=lambda: res.setdefault("once", brain.say_once(FRESH, "Скажи что-нибудь доброе.")))
    th.start()
    both = "".join(brain.stream_reply(FRESH, [], text="как дела?", lang="ru"))
    th.join(60)
    assert both.strip() and res.get("once"), "одновременные запросы"
    print(f"\nИТОГ: {score}/{len(TESTS)}, первая фраза медиана {statistics.median(firsts):.2f} с, "
          f"история из 20 реплик: первое слово {t_hist:.2f} с, после сдвига истории {t_shift:.2f} с, "
          f"история выросла на реплику {t_grow:.2f} с; два запроса сразу — оба ответили")
    print("chat:", brain.chat([{"role": "user", "content": "Ответь одним словом: столица Кореи?"}]).strip())
    ok = score >= 13 and statistics.median(firsts) <= 1.0 and max(t_hist, t_shift) < 2 and t_grow < 1
    print("OK" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
