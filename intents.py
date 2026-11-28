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


# Команды музыке, громкости и таймеру: сразу, без мозга (модель их иногда пропускает).
DEVICE = [  # порядок важен: громкость раньше музыки («поставь музыку потише»), «выключи музыку» раньше «включи музыку»
    ("ГРОМКОСТЬ +10", ["громче", "погромче", "прибавь звук", "прибавь громкость", "louder", "turn it up",
                       "volume up", "소리 키워", "볼륨 올려", "크게 해"]),
    ("ГРОМКОСТЬ -10", ["тише", "потише", "убавь звук", "убавь громкость", "quieter", "turn it down",
                       "volume down", "소리 줄여", "볼륨 내려", "작게 해"]),
    ("ГРОМКОСТЬ mute", ["выключи звук", "без звука", "убери звук", "mute", "음소거"]),
    ("МУЗЫКА pause", ["поставь на паузу", "на паузу", "пауза", "останови музыку", "выключи музыку", "стоп музыка",
                      "выключи песню", "pause music", "pause", "stop music", "음악 꺼", "노래 꺼", "일시정지", "음악 멈춰"]),
    ("МУЗЫКА next", ["следующая песня", "следующий трек", "следующую песню", "следующую", "следующая",
                     "переключи песню", "переключи трек", "другую песню", "next song", "next track", "skip song",
                     "skip", "다음 곡", "다음 노래"]),
    ("МУЗЫКА prev", ["предыдущая песня", "предыдущую песню", "прошлую песню", "предыдущий трек", "верни песню",
                     "previous song", "previous track", "이전 곡", "이전 노래"]),
    ("МУЗЫКА play", ["включи музыку", "поставь музыку", "включи песню", "включи музычку", "вруби музыку",
                     "врубай музыку", "продолжи музыку", "play music", "play some music", "resume music",
                     "음악 틀어", "노래 틀어", "음악 켜", "노래 켜"]),
]
_NO_FUZZY = {"ГРОМКОСТЬ mute", "МУЗЫКА pause"}
NOT_DEVICE = ["не включай", "не выключай", "не ставь", "не надо", "не делай", "don t", "do not", "하지 마", "틀지 마", "끄지 마"]
_DEVICE_FILLER = r"\b(пожалуйста|please|подруга|ань|аня|алиса|таня|давай|можешь|сделай|чуть|ещ[её]|немного|немножко|" \
                 r"а|ну|ка|можно|hey|can you|could you|a bit|little)\b"
_NUM = {"один": 1, "одну": 1, "две": 2, "два": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8,
        "девять": 9, "десять": 10, "пятнадцать": 15, "двадцать": 20, "тридцать": 30, "минуту": 1, "one": 1, "two": 2,
        "three": 3, "five": 5, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30}
_TIMER = [r"таймер\w*\s+на\s+(\w+)\s*(?:минут\w*)?", r"(?:set\s+)?(?:a\s+)?timer\s+for\s+(\w+)",
          r"(\d+)\s*분\s*(?:타이머|뒤|후)"]


def device_command(text: str) -> str | None:
    """Готовая команда для handle_commands: «МУЗЫКА play|pause|next|prev», «ГРОМКОСТЬ +10|-10|mute»,
    «ТАЙМЕР N | таймер» — или None (длинная фраза, отрицание, разговор о музыке)."""
    t = norm(text)
    if not t or len(t.split()) > 7 or any(p in t for p in NOT_DEVICE) or t.startswith("не "):
        return None
    for rx in _TIMER:
        m = re.search(rx, t)
        if m:
            n = m.group(1)
            n = int(n) if n.isdigit() else _NUM.get(n)
            if n and 0 < n <= 600:
                return f"ТАЙМЕР {n} | таймер"
            return None
    t = " ".join(re.sub(_DEVICE_FILLER, " ", t).split())
    if not t:
        return None
    for fuzzy in (False, True):                          # сначала точно (иначе «включи» ≈ «выключи»), потом с опечатками
        for cmd, phrases in DEVICE:
            for p in phrases:
                if len(t.split()) > len(p.split()) + 2:  # «тише едешь — дальше будешь» — не команда
                    continue
                if cmd.startswith("МУЗЫКА") and " " not in p and t != p:
                    continue                             # «skip», «следующая» — только сами по себе («а какая следующая?» — вопрос)
                if fuzzy and cmd in _NO_FUZZY:
                    continue                             # «включи звук» ≈ «выключи звук» — наоборот, не гадаем
                if (re.search(rf"(^|\s){re.escape(p)}", t) if not fuzzy else len(p) > 8 and _near(p, t, 0.88)):
                    return cmd
    return None


# «Повтори за мной …» — сразу, без мозга: модель отказывается повторять ругательства и путается.
_REP_OFF = re.compile(r"(хватит|перестань|прекрати|стоп|не надо|больше не)\s+(повторять|повторяй)|stop repeating|"
                      r"그만 따라", re.I)
_REP_ON = re.compile(r"(начни|начинай|можешь начать|давай|будешь)\s+(ты\s+)?(повторять|повторяй)|^повторяй\b|"
                     r"(повторяй|повторять)\s+(за мной|вс[её]|то,? что я)|keep repeating|repeat everything", re.I)
_REP_AGAIN = re.compile(r"^(а\s+)?повтори\s*(ещ[её] раз|снова|что ты сказала|последнее)?\s*[.!?]?$|"
                        r"^повтори\s+(ещ[её] раз|что ты сказала)", re.I)
_REP_SAY = re.compile(r"(?:повтори|скажи)\s+за\s+мной[\s:,.\-—]*(.+)|^повтори[\s:,\-—]+(?!ещ[её]|что ты|это\b)(.+)|"
                      r"repeat after me[\s:,]*(.+)|^repeat[\s:,]+(.+)", re.I)
_REP_BEFORE = re.compile(r"^(.+?)[\s,.\-—]+(?:повтори|скажи)\s*(это|за мной)?\s*[.!?]*$|^(.+?)\s*따라\s*(해|말해)", re.I)


def repeat_command(text: str):
    """('say', слова) | ('on', '') | ('off', '') | ('again', '') | None."""
    t = (text or "").strip()
    low = t.lower().replace("ё", "е")
    if not low:
        return None
    if _REP_OFF.search(low):
        return ("off", "")
    if _REP_ON.search(low):
        return ("on", "")
    if _REP_AGAIN.search(low):
        return ("again", "")
    for rx in (_REP_SAY, _REP_BEFORE):
        m = rx.search(t)
        if m:
            words = next((g for g in m.groups() if g and g.lower() not in ("это", "за мной", "해", "말해")), "")
            words = words.strip(" \t,.:;!?—-«»\"")
            if words and not re.fullmatch(r"(это|за мной)", words.lower()):
                return ("say", words)
    return None


if __name__ == "__main__":
    for s in ["Можешь присесть?", "Присядь, пожалуйста", "Ляг", "Аня, походи туда-обратно", "Встань", "Как дела?",
              "Сядь на поезд и приезжай ко мне завтра утром", "Не садись", "sit down please", "앉아봐", "стой", "Ты устала?"]:
        print(f"{body_command(s)!s:6} {s}")
if __name__ == "__main__":
    for s in ["Спокойной ночи.", "Всё, иди спать, спокойной ночи.", "Эй, что такое? Иди спать! Спокойной ночи!",
              "Спокойно ночи", "Всё, давай спокойно.", "Не спи ещё", "Как дела?", "споки ноки", "Иди, поспи"]:
        print(f"{is_sleep(s)!s:5}  {s}")


def task_command(text: str) -> str | None:
    """«Включи <песня> в ютуб музыке», «найди на ютубе …», «найди … на купанге» — она сама делает
    на экране («глаза и руки», recipes.py). Возвращает «СДЕЛАТЬ <его слова>» или None."""
    import recipes
    if recipes.find(text) is None:
        return None
    return "СДЕЛАТЬ " + text.strip()


# --- сам Mac (mac.py) и экран: сразу, без мозга ---
_MAC_FILLER = r"\b(пожалуйста|please|подруга|ань|аня|алиса|таня|давай|можешь|мне|ка|ну|а|быстро|сейчас|plz)\b"
_QUIT = re.compile(r"^(?:закрой|закрыть|выключи|выруби|заверши|выйди из|закрой программу|выключи программу|"
                   r"quit|close)\s+(.+)$")
_SHOT = ["сделай скриншот", "сделай скрин", "скриншот экрана", "сделай снимок экрана", "сфоткай экран",
         "заскринь", "скринь", "take a screenshot", "screenshot", "스크린샷", "화면 캡처", "캡처해"]
_SHOW_FOLDER = re.compile(r"^(?:открой|покажи|открыть|зайди в|open|show)\s+(?:папку\s+|мне\s+)?(.+)$")
_FIND_FILE = re.compile(r"^(?:найди|поищи|где|где лежит|найти|find|where is)\s+(?:мой\s+|мою\s+|мне\s+)?"
                        r"(?:файл|документ|папку|фотку|фото|картинку|презентацию|таблицу|file|document)\w*\s+"
                        r"(?:с названием\s+|под названием\s+|называется\s+|про\s+)?(.+)$")
_SCREEN = re.compile(r"(прочитай|прочти|зачитай|переведи|перескажи|о ч[её]м|что\s+(?:тут|здесь|на экране)"
                     r"\s+написано|read|translate|summari[sz]e|번역|읽어)")
_SCREEN_WHERE = re.compile(r"(экран|тут|здесь|страниц|стать|текст|письм|сообщени|сайт|screen|page|text|화면)")
_SCREEN_THIS = re.compile(r"^(прочитай|прочти|зачитай|переведи|перескажи|read|translate)\s+(это|эту|этот|this)"
                          r"(\s+на\s+\w+)?$")
_MOVE = re.compile(r"(?:(?:перейди|переходи|иди|пойди|перебирайся|переместись|приходи|come|go|move)\w*\s+|^)"
                   r"(?:ко\s+)?(?:на|в|to)\s+(?:этот|тот|другой|второй|мой|соседний|главный|this|other|my)?\s*"
                   r"(экран|монитор|рабочий стол|screen|monitor|display)\b")


def mac_command(text: str):
    """('quit', программа) | ('shot', '') | ('folder', путь) | ('find', что) | ('read'|'translate'|'summary', язык)
    | ('screen', 'mouse'|'next') | None."""
    import mac
    t = norm(text)
    if not t or len(t.split()) > 12 or t.startswith("не "):
        return None
    t = " ".join(re.sub(_MAC_FILLER, " ", t).split())
    m = _MOVE.search(t)
    if m:
        return ("screen", "next" if re.search(r"другой|второй|соседний|other|\bтот\b", t) else "mouse")
    if any(p == t or (len(p) > 6 and p in t) for p in _SHOT) and len(t.split()) <= 5:
        return ("shot", "")
    if _SCREEN.search(t) and (_SCREEN_WHERE.search(t) or _SCREEN_THIS.search(t)) and "ютуб" not in t:
        if re.search(r"переведи|translate|번역", t):
            to = "en" if re.search(r"на английск|in english|to english", t) else \
                 "ko" if re.search(r"на корейск|in korean|to korean|한국어로", t) else "ru"
            return ("translate", to)
        if re.search(r"перескажи|о ч[её]м|summari", t):
            return ("summary", "ru")
        return ("read", "ru")
    m = _FIND_FILE.search(t)
    if m and len(m.group(1).split()) <= 5:
        return ("find", m.group(1).strip())
    m = _SHOW_FOLDER.search(t)
    if m and len(m.group(1).split()) <= 3:
        p = mac.folder_for(m.group(1))
        if p is not None:
            return ("folder", str(p))
    m = _QUIT.search(t)
    if m and len(m.group(1).split()) <= 3:
        what = m.group(1)
        if any(w in what for w in ("музык", "песн", "звук", "видео", "трек", "свет", "music", "sound")):
            return None                                  # «выключи музыку» — это device_command
        app = mac.find_running(what)
        if app:
            return ("quit", app)
    return None
