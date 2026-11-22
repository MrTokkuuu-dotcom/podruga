"""Команды, на которые она отвечает сразу, прямо на Mac, без Google: «спокойной ночи», «иди спать».
Сравнение гибкое: Whisper может написать слово чуть иначе («спокойно ночи», «споки»)."""
import re
from difflib import SequenceMatcher

SLEEP = ["спокойной ночи", "доброй ночи", "иди спать", "ложись спать", "пора спать", "спать иди",
         "иди поспи", "отдыхай подруга", "пока подруга", "споки ноки", "сладких снов", "засыпай",
         "good night", "goodnight", "nighty night", "sweet dreams", "night night",
         "잘 자", "잘자", "굿나잇", "좋은 꿈 꿔", "이제 자", "가서 자", "자러 가", "잘 자요"]
NOT_SLEEP = ["не спи", "не ложись", "не иди спать", "не засыпай", "рано спать", "не хочу спать",
             "don t sleep", "don t go", "not sleepy", "not good night", "자지 마", "안 자", "잘 잤"]


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


# Команды телу: сразу, без Google. Короткие фразы («присядь», «можешь присесть?», «походи туда-обратно»).
BODY = {
    "sit": ["присядь", "присесть", "сядь", "садись", "сесть", "посиди", "присаживайся", "можешь сесть", "сядь на пол",
            "sit down", "take a seat", "have a seat", "sit", "앉아", "앉아봐", "앉아 줘", "앉을래"],
    "lie": ["ляг", "ложись", "приляг", "полежи", "лечь", "прилечь", "можешь лечь",
            "lie down", "lay down", "누워", "누워봐", "누워 줘"],
    "stand": ["встань", "вставай", "поднимись", "встать", "stand up", "get up", "일어나", "일어서"],
    "pace": ["походи туда обратно", "походи туда сюда", "погуляй туда сюда", "ходи туда сюда", "туда сюда",
             "туда обратно", "походи", "погуляй", "пройдись", "прогуляйся",
             "walk around", "walk back and forth", "go for a walk", "왔다 갔다", "걸어봐", "산책해"],
    "left": ["иди влево", "иди налево", "влево", "налево", "go left", "왼쪽으로"],
    "right": ["иди вправо", "иди направо", "вправо", "направо", "go right", "오른쪽으로"],
    "stop": ["стой", "стоп", "остановись", "замри", "stop", "멈춰", "그만 걸어"],
}
NOT_BODY = ["не садись", "не сядь", "не ложись", "не ляг", "не вставай", "не ходи", "не надо", "не уходи",
            "don t sit", "don t lie", "don t go", "앉지 마", "눕지 마"]
_NOT_BODY_TOPIC = ["музык", "песн", "трек", "видео", "ютуб", "music", "song", "video", "노래", "음악", "영상"]
# «сядь» внутри длинной фразы о другом («сядь на поезд», «посиди подумай над задачей») — не команда
_BODY_MAX_WORDS = 6


def body_command(text: str) -> str | None:
    """'sit' | 'lie' | 'stand' | 'pace' | 'left' | 'right' | 'stop' или None."""
    t = norm(text)
    if not t or len(t.split()) > _BODY_MAX_WORDS or any(p in t for p in NOT_BODY) or any(w in t for w in _NOT_BODY_TOPIC):
        return None
    t = re.sub(r"\b(пожалуйста|please|подруга|ань|аня|алиса|таня|давай|можешь|а|ну|ка|please)\b", " ", t)
    t = " ".join(t.split())
    for kind in ("pace", "sit", "lie", "stand", "left", "right", "stop"):   # «походи туда-обратно» раньше «стоп»
        for p in BODY[kind]:
            if (len(p) <= 4 and re.search(rf"(^|\s){re.escape(p)}($|\s)", t)) or (len(p) > 4 and _near(p, t, 0.86)):
                return kind
    return None


if __name__ == "__main__":
    for s in ["Можешь присесть?", "Присядь, пожалуйста", "Ляг", "Аня, походи туда-обратно", "Встань", "Как дела?",
              "Сядь на поезд и приезжай ко мне завтра утром", "Не садись", "sit down please", "앉아봐", "стой", "Ты устала?"]:
        print(f"{body_command(s)!s:6} {s}")
if __name__ == "__main__":
    for s in ["Спокойной ночи.", "Всё, иди спать, спокойной ночи.", "Эй, что такое? Иди спать! Спокойной ночи!",
              "Спокойно ночи", "Всё, давай спокойно.", "Не спи ещё", "Как дела?", "споки ноки", "Иди, поспи"]:
        print(f"{is_sleep(s)!s:5}  {s}")
