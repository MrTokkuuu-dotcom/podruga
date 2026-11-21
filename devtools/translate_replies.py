"""Перевод готовых ответов (replies*.txt) на английский и корейский через Gemini — с проверкой формата.
Запуск из папки репозитория (ключ берётся из ~/Podruga/.env, на экран не выводится):
    ~/Podruga/venv/bin/python devtools/translate_replies.py en      # или ko
Пишет replies_<имя>_en.txt / _ko.txt рядом. Уже готовые файлы пропускает (удали, чтобы перевести заново)."""
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from config import _load_env_file  # noqa: E402

_load_env_file()
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

LANG = sys.argv[1]
MODEL = os.environ.get("TR_MODEL", "gemini-3.5-flash-lite")   # у flash бесплатно всего 20 запросов в день
CHUNK = 10
NAME = {"en": "английский", "ko": "корейский"}[LANG]
STYLE = {
    "en": "живой разговорный английский, как говорит близкая подруга (warm, casual, short).",
    "ko": "живой разговорный корейский на 반말, как говорит близкая подруга (따뜻하고 짧게). Не используй ханча.",
}[LANG]
EX = {"en": "Good morning, {user}! How did you sleep?", "ko": "좋은 아침, {user}! 잘 잤어?"}[LANG]
RULES = f"""Переведи кусок файла готовых ответов голосового ИИ-компаньона на {NAME} язык. Стиль: {STYLE}
Формат строк — сохрани ТОЧНО:
- «## название» — НЕ переводить, оставить как есть, ровно те же строки в том же порядке.
- «@всегда», «@ответ», «@служебное», «@своё» — оставить как есть.
- «? фраза» — как ОН может это сказать. Переведи на {NAME}, в нижнем регистре, без знаков препинания.
  Дай 2–5 разных естественных вариантов (каждый отдельной строкой «? ...»), как реально говорят.
  Плейсхолдеры {{n}} и {{что}} сохрани. «*» в конце слова — только если это латиница/английский.
- «! КОМАНДА ...» — оставить как есть, не переводить.
- Строки ответов (всё остальное): метки в начале строки — «[утро]/[день]/[вечер]/[ночь]», «<аня>/<алиса>/<таня>»,
  «{{радость}}» и другие эмоции в фигурных скобках — оставить по-русски как есть. А ТЕКСТ ответа после меток
  ОБЯЗАТЕЛЬНО перевести — ни одного русского слова в тексте ответов и в «?»-фразах.
  Пример: «[утро] {{радость}} Доброе утро, {{user}}! Как спалось?» → «[утро] {{радость}} {EX}»
- Плейсхолдеры {{user}} {{name}} {{time}} {{date}} {{weekday}} {{daypart}} {{n}} {{что}} — сохранить как есть.
- Строки, начинающиеся с «#» (не «##»), — удалить.
- Шутки и загадки адаптируй так, чтобы были смешными на {NAME} (не дословно). Русские реалии — заменить уместными.
Верни ТОЛЬКО переведённый текст в том же формате, без пояснений и без ``` ."""


def chunks(text: str):
    secs, cur = [], []
    for line in text.splitlines():
        if line.startswith("## ") and cur:
            secs.append(cur)
            cur = []
        if line.startswith("#") and not line.startswith("## "):
            continue
        cur.append(line)
    if cur:
        secs.append(cur)
    secs = [s for s in secs if any(x.startswith("## ") for x in s)]
    for i in range(0, len(secs), CHUNK):
        yield "\n".join("\n".join(s) for s in secs[i:i + CHUNK])


EMO = {"радость", "нежность", "смущение", "удивление", "грусть", "задумчивость", "спокойствие"}
PH = re.compile(r"\{(user|name|time|date|weekday|daypart|n|что)\}")


def check(src: str, out: str) -> str | None:
    hs = [l for l in src.splitlines() if l.startswith("## ")]
    ho = [l for l in out.splitlines() if l.startswith("## ")]
    if hs != ho:
        return f"заголовки разделов не совпали ({len(hs)} → {len(ho)})"
    if sorted(PH.findall(src)) and not set(PH.findall(out)) <= set(PH.findall(src)) | {"user", "name"}:
        return "лишние плейсхолдеры"
    ans_src = sum(1 for l in src.splitlines() if l and l[0] not in "#?!@")
    ans_out = sum(1 for l in out.splitlines() if l and l[0] not in "#?!@")
    if ans_out < ans_src * 0.9:
        return f"потерялись ответы ({ans_src} → {ans_out})"
    if LANG == "ko" and not re.search(r"[가-힣]", out):
        return "нет корейских букв"
    tags = set(re.findall(r"\{([^}]*)\}", out)) - {"user", "name", "time", "date", "weekday", "daypart", "n", "что"}
    if not tags <= EMO:
        return f"испорченные метки: {sorted(tags - EMO)[:3]}"
    if not set(re.findall(r"\[([^\]]*)\]", out)) <= {"утро", "день", "вечер", "ночь"} \
            or not set(re.findall(r"<([^>]*)>", out)) <= {"аня", "алиса", "таня"}:
        return "испорченные метки времени/девочек"
    if re.search(r"[А-Яа-яЁё]", re.sub(r"\{[^}]*\}|\[[^\]]*\]|<[^>]*>|^## .*$|^!.*$|^@.*$", "", out, flags=re.M)):
        return "остался русский текст"
    return None


def main():
    client = genai.Client(http_options=types.HttpOptions(timeout=120_000))
    files = [REPO / "replies.txt", *sorted(p for p in REPO.glob("replies_*.txt") if not re.search(r"_(en|ko)$", p.stem))]
    for src_path in files:
        stem = "replies_0_osnova" if src_path.name == "replies.txt" else src_path.stem
        dst = REPO / f"{stem}_{LANG}.txt"
        if dst.exists():
            print(f"{dst.name}: уже есть — пропускаю")
            continue
        parts = []
        for k, chunk in enumerate(chunks(src_path.read_text(encoding="utf-8"))):
            for attempt in range(5):
                try:
                    r = client.models.generate_content(model=MODEL, contents=RULES + "\n\n" + chunk,
                                                       config=types.GenerateContentConfig(temperature=0.4))
                    out = (r.text or "").strip().strip("`").strip()
                except Exception as e:
                    out, err = "", f"ошибка Google: {e}"
                else:
                    err = check(chunk, out)
                if not err:
                    break
                print(f"  {src_path.name} кусок {k + 1}: {err[:120]} — пробую ещё раз", flush=True)
                if "RESOURCE_EXHAUSTED" in err and "PerDay" in err:
                    sys.exit("дневной лимит Google исчерпан — запусти завтра, готовые куски сохранены")
                time.sleep(20 if "429" in err or "503" in err else 3)
            if err:
                print(f"  {src_path.name} кусок {k + 1}: НЕ ВЫШЛО ({err}) — пропускаю кусок", flush=True)
                continue
            parts.append(out)
            print(f"  {src_path.name} кусок {k + 1}: ок", flush=True)
            time.sleep(4)                                   # бесплатный лимит — не больше ~15 запросов в минуту
        head = f"# Готовые ответы — {NAME} (перевод {src_path.name} через Gemini, проверен по формату). Формат — как в replies.txt.\n\n"
        dst.write_text(head + "\n\n".join(parts) + "\n", encoding="utf-8")
        print(f"{dst.name}: записано", flush=True)


if __name__ == "__main__":
    main()
