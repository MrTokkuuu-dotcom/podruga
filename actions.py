"""Что она умеет делать на Mac по просьбе. Только из этого списка — ничего не удаляет,
не покупает и не отправляет. Команды приходят из ответа мозга в виде <<КОМАНДА ...>>."""
import re
import subprocess
import sys
import urllib.parse

SITES = {
    # YouTube Music — раньше обычного YouTube, иначе «ютуб музыку» искалось бы на YouTube как «музыку»
    "youtube music": "https://music.youtube.com", "ютуб музык": "https://music.youtube.com",
    "ютуб мьюзик": "https://music.youtube.com", "ютуб мюзик": "https://music.youtube.com",
    "yt music": "https://music.youtube.com", "유튜브 뮤직": "https://music.youtube.com",
    "youtube": "https://www.youtube.com", "ютуб": "https://www.youtube.com",
    "google": "https://www.google.com", "гугл": "https://www.google.com",
    "gmail": "https://mail.google.com", "почта": "https://mail.google.com",
    "naver": "https://www.naver.com", "навер": "https://www.naver.com",
    "coupang": "https://www.coupang.com", "купанг": "https://www.coupang.com",
    "instagram": "https://www.instagram.com", "инстаграм": "https://www.instagram.com",
    "tiktok": "https://www.tiktok.com", "тикток": "https://www.tiktok.com",
    "netflix": "https://www.netflix.com", "нетфликс": "https://www.netflix.com",
    "papago": "https://papago.naver.com", "папаго": "https://papago.naver.com",
    "карты": "https://map.naver.com", "погода": "https://weather.naver.com",
    "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai",
    # корейские названия
    "유튜브": "https://www.youtube.com", "구글": "https://www.google.com", "지메일": "https://mail.google.com",
    "네이버": "https://www.naver.com", "쿠팡": "https://www.coupang.com", "인스타그램": "https://www.instagram.com",
    "인스타": "https://www.instagram.com", "틱톡": "https://www.tiktok.com", "넷플릭스": "https://www.netflix.com",
    "파파고": "https://papago.naver.com", "지도": "https://map.naver.com", "날씨": "https://weather.naver.com",
    "챗지피티": "https://chatgpt.com", "maps": "https://map.naver.com", "weather": "https://weather.naver.com",
}
APPS = {
    "telegram": "Telegram", "телеграм": "Telegram", "kakaotalk": "KakaoTalk", "какао": "KakaoTalk",
    "музыка": "Music", "music": "Music", "spotify": "Spotify", "спотифай": "Spotify",
    "заметки": "Notes", "notes": "Notes", "календарь": "Calendar", "calendar": "Calendar",
    "safari": "Safari", "сафари": "Safari", "chrome": "Google Chrome", "хром": "Google Chrome",
    "finder": "Finder", "файндер": "Finder", "калькулятор": "Calculator",
    "capcut": "CapCut", "капкат": "CapCut", "terminal": "Terminal", "терминал": "Terminal",
    "텔레그램": "Telegram", "카카오톡": "KakaoTalk", "카톡": "KakaoTalk", "음악": "Music", "스포티파이": "Spotify",
    "메모": "Notes", "캘린더": "Calendar", "달력": "Calendar", "사파리": "Safari", "크롬": "Google Chrome",
    "파인더": "Finder", "계산기": "Calculator", "calculator": "Calculator", "캡컷": "CapCut", "터미널": "Terminal",
    "디스코드": "Discord", "discord": "Discord", "스팀": "Steam", "steam": "Steam",
}


def _osa(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return r.stdout.strip()


def known_target(what: str) -> bool:
    """Ссылка или знакомый сайт/программа — тогда «открой …» можно сделать сразу, без мозга."""
    low = what.strip().strip("«»\"'").lower()
    if low.startswith(("http://", "https://")):
        return True
    rest = low
    for k in list(SITES) + list(APPS):
        if k in rest:
            rest = rest.replace(k, " ")
    return rest != low and len(rest.split()) <= 2      # «ютуб», «ютуб котики» — да; длинная просьба — мозгу


def open_thing(what: str) -> str:
    w = what.strip().strip("«»\"'")
    low = w.lower()
    if low.startswith(("http://", "https://")):
        subprocess.run(["open", w], check=True)
        return f"открыла {w}"
    for k, url in SITES.items():
        if k in low:
            # «youtube котики» → поиск на YouTube
            rest = low.replace(k, "").strip(" :—-")
            if rest and url == "https://www.youtube.com":
                url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(rest)
            subprocess.run(["open", url], check=True)
            return f"открыла {k}"
    for k, app in APPS.items():
        if k in low:
            subprocess.run(["open", "-a", app], check=True)
            return f"открыла {app}"
    r = subprocess.run(["open", "-a", w], capture_output=True)
    if r.returncode == 0:
        return f"открыла {w}"
    # не нашла приложение — ищем в интернете
    subprocess.run(["open", "https://www.google.com/search?q=" + urllib.parse.quote(w)], check=True)
    return f"поискала «{w}» в браузере"


def music(cmd: str, sound: bool | None = None) -> str:
    """Пауза / дальше / назад / включи — тому, что сейчас играет (mac.py): Spotify, «Музыка»
    или браузер (YouTube Music, YouTube) через кнопки ⏯ ⏭ ⏮."""
    import mac
    return mac.music(cmd, sound)


def volume(arg: str) -> str:
    a = arg.strip().lower().replace("%", "")
    if a in ("mute", "без звука", "выкл"):
        _osa("set volume output muted true")
        return "звук выключен"
    m = re.match(r"([+-]?)\s*(\d{1,3})", a)
    if not m:
        raise ValueError(f"не поняла громкость: {arg}")
    sign, n = m.group(1), int(m.group(2))
    if sign:
        cur = int(_osa("output volume of (get volume settings)") or 50)
        n = cur + n if sign == "+" else cur - n
    n = max(0, min(100, n))
    _osa(f"set volume output volume {n}")
    _osa("set volume output muted false")
    return f"громкость {n}%"


def run(kind: str, arg: str, sound: bool | None = None) -> str:
    """Выполнить команду. Возвращает короткое описание для журнала."""
    if sys.platform != "darwin":
        return "команды на компьютере пока только для Mac"
    kind = kind.upper()
    if kind == "ОТКРЫТЬ":
        return open_thing(arg)
    if kind == "МУЗЫКА":
        return music(arg, sound)
    if kind == "ГРОМКОСТЬ":
        return volume(arg)
    raise ValueError(f"не знаю команду {kind}")
