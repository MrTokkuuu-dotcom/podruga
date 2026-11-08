"""Команды, на которые она отвечает сразу, прямо на Mac, без Google: «спокойной ночи», «иди спать».
Сравнение гибкое: Whisper может написать слово чуть иначе («спокойно ночи», «споки»)."""
import re
from difflib import SequenceMatcher

SLEEP = ["спокойной ночи", "доброй ночи", "иди спать", "ложись спать", "пора спать", "спать иди",
         "иди поспи", "отдыхай подруга", "пока подруга", "споки ноки", "сладких снов", "засыпай"]
NOT_SLEEP = ["не спи", "не ложись", "не иди спать", "не засыпай", "рано спать", "не хочу спать"]


def norm(text: str) -> str:
    text = re.sub(r"[^\w\s-]", " ", text.lower().replace("ё", "е"))
    return " ".join(text.split())


def _near(phrase: str, text: str, cutoff: float) -> bool:
    """Есть ли в тексте кусок, похожий на фразу (по буквам, с запасом на опечатки распознавания)."""
    if phrase in text:
        return True
    ws, n = text.split(), len(phrase.split())
    for k in (n, n + 1):
        for i in range(0, max(1, len(ws) - k + 1)):
            if SequenceMatcher(None, phrase, " ".join(ws[i:i + k])).ratio() >= cutoff:
                return True
    return False


def is_sleep(text: str) -> bool:
    t = norm(text)
    if not t or len(t.split()) > 12 or any(p in t for p in NOT_SLEEP):
        return False
    return any(_near(p, t, 0.84) for p in SLEEP)


if __name__ == "__main__":
    for s in ["Спокойной ночи.", "Всё, иди спать, спокойной ночи.", "Эй, что такое? Иди спать! Спокойной ночи!",
              "Спокойно ночи", "Всё, давай спокойно.", "Не спи ещё", "Как дела?", "споки ноки", "Иди, поспи"]:
        print(f"{is_sleep(s)!s:5}  {s}")
