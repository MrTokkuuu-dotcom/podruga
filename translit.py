"""Английские слова — русскими буквами, только для голоса. Русский голос (Silero) латиницу просто
пропускает: «Давай сыграем в Valorant» звучало как «Давай сыграем». На экране текст остаётся как есть.
Сначала словарь (как это говорят по-русски), потом простые правила для незнакомых слов."""
import re

WORDS = {
    "youtube": "ютуб", "discord": "дискорд", "valorant": "валорант", "steam": "стим", "minecraft": "майнкрафт",
    "genshin": "геншин", "impact": "импакт", "telegram": "телеграм", "spotify": "спотифай", "kakaotalk": "какао ток",
    "netflix": "нетфликс", "tiktok": "тик ток", "instagram": "инстаграм", "chatgpt": "чат джи пи ти",
    "gpt": "джи пи ти", "claude": "клод", "google": "гугл", "gemini": "джемини", "capcut": "кап кат",
    "league": "лига", "legends": "легенд", "counter-strike": "контр страйк", "cs": "кс", "dota": "дота",
    "roblox": "роблокс", "fortnite": "фортнайт", "pubg": "пабг", "overwatch": "овервотч", "mac": "мак",
    "macbook": "макбук", "iphone": "айфон", "ipad": "айпад", "apple": "эпл", "windows": "виндоус",
    "wi-fi": "вай фай", "wifi": "вай фай", "ok": "окей", "okay": "окей", "email": "имейл", "zoom": "зум",
    "safari": "сафари", "chrome": "хром", "whatsapp": "вотсап", "twitch": "твич", "stream": "стрим",
    "facebook": "фейсбук", "twitter": "твиттер", "reddit": "реддит", "github": "гитхаб", "excel": "эксель",
    "word": "ворд", "photoshop": "фотошоп", "premiere": "премьер", "final": "файнал", "cut": "кат",
    "pro": "про", "max": "макс", "plus": "плюс", "online": "онлайн", "game": "гейм", "of": "оф", "the": "зе",
    "and": "энд", "how": "хау", "are": "ар", "what": "вот", "doing": "дуинг", "now": "нау", "right": "райт",
    "my": "май", "your": "ёр", "is": "из", "it": "ит", "to": "ту", "me": "ми", "we": "ви", "good": "гуд", "hello": "хеллоу", "hi": "хай", "hey": "хей", "bye": "бай", "yes": "йес", "no": "ноу",
    "thanks": "сенкс", "sorry": "сорри", "cool": "кул", "nice": "найс", "love": "лав", "you": "ю",
    "elden": "элден", "ring": "ринг", "call": "колл", "duty": "дьюти", "apex": "апекс", "battlefield": "батлфилд",
    "gta": "джи ти эй", "fifa": "фифа", "sims": "симс", "witcher": "ведьмак", "cyberpunk": "киберпанк",
    "kakao": "какао", "naver": "навер", "coupang": "купанг", "lol": "лол", "vs": "версус", "ai": "эй ай",
    "vrm": "ви ар эм", "vroid": "вироид", "usb": "ю эс би", "ps5": "пи эс пять", "xbox": "иксбокс",
    "nintendo": "нинтендо", "switch": "свитч", "playstation": "плейстейшн",
}

# буквосочетания → звуки (по порядку: длинные раньше коротких)
RULES = [
    ("tion", "шн"), ("sion", "жн"), ("ough", "аф"), ("igh", "ай"), ("sch", "ск"), ("tch", "ч"),
    ("sh", "ш"), ("ch", "ч"), ("th", "т"), ("ph", "ф"), ("ck", "к"), ("qu", "кв"), ("wh", "в"),
    ("oo", "у"), ("ee", "и"), ("ea", "и"), ("ai", "ей"), ("ay", "ей"), ("oy", "ой"), ("ow", "оу"),
    ("ou", "ау"), ("au", "о"), ("ie", "и"), ("ey", "ей"), ("kn", "н"), ("wr", "р"), ("ng", "нг"),
    ("x", "кс"), ("j", "дж"), ("w", "в"), ("y", "и"), ("c", "к"), ("q", "к"),
    ("a", "а"), ("b", "б"), ("d", "д"), ("e", "е"), ("f", "ф"), ("g", "г"), ("h", "х"), ("i", "и"),
    ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("r", "р"), ("s", "с"),
    ("t", "т"), ("u", "а"), ("v", "в"), ("z", "з"),
]
_RX = re.compile(r"[A-Za-z][A-Za-z\-']*")
DIGITS = {"0": "ноль", "1": "один", "2": "два", "3": "три", "4": "четыре", "5": "пять", "6": "шесть",
          "7": "семь", "8": "восемь", "9": "девять"}


def _by_rules(w: str) -> str:
    w = w.lower().replace("'", "")
    m = re.match(r"^(.*?)([aiou])([bcdfgklmnprstvz])e$", w)
    if m and len(w) > 3:                            # «немая e»: game → гейм, time → тайм, gate → гейт
        long = {"a": "ей", "i": "ай", "o": "оу", "u": "ю"}[m.group(2)]
        return _by_rules(m.group(1)) + long + _by_rules(m.group(3))
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    out, i = "", 0
    while i < len(w):
        for a, b in RULES:
            if w.startswith(a, i):
                out += b
                i += len(a)
                break
        else:
            out += " " if w[i] == "-" else ""
            i += 1
    return out


def word(w: str) -> str:
    low = w.lower()
    if low in WORDS:
        return WORDS[low]
    if "-" in low and all(p in WORDS for p in low.split("-")):
        return " ".join(WORDS[p] for p in low.split("-"))
    if w.isupper() and 2 <= len(w) <= 4:            # сокращение: «NPC» → «эн пи си»
        names = {"a": "эй", "b": "би", "c": "си", "d": "ди", "e": "и", "f": "эф", "g": "джи", "h": "эйч",
                 "i": "ай", "j": "джей", "k": "кей", "l": "эл", "m": "эм", "n": "эн", "o": "оу", "p": "пи",
                 "q": "кью", "r": "ар", "s": "эс", "t": "ти", "u": "ю", "v": "ви", "w": "дабл ю", "x": "икс",
                 "y": "уай", "z": "зет"}
        return " ".join(names.get(ch, "") for ch in low)
    return _by_rules(w)


def speakable(text: str) -> str:
    """Текст для русского голоса: латиница → кириллица."""
    if not re.search(r"[A-Za-z]", text):
        return text
    text = re.sub(r"(?i)\b([a-z]+)(\d)\b", lambda m: m.group(1) + " " + DIGITS[m.group(2)], text)  # PS5
    return _RX.sub(lambda m: word(m.group(0)), text)
