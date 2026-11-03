"""Что она умеет делать на Mac по просьбе. Только из этого списка — ничего не удаляет,
не покупает и не отправляет. Команды приходят из ответа мозга в виде <<КОМАНДА ...>>."""
import re
import subprocess
import sys
import urllib.parse

SITES = {
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
}
APPS = {
    "telegram": "Telegram", "телеграм": "Telegram", "kakaotalk": "KakaoTalk", "какао": "KakaoTalk",
    "музыка": "Music", "music": "Music", "spotify": "Spotify", "спотифай": "Spotify",
    "заметки": "Notes", "notes": "Notes", "календарь": "Calendar", "calendar": "Calendar",
    "safari": "Safari", "сафари": "Safari", "chrome": "Google Chrome", "хром": "Google Chrome",
    "finder": "Finder", "файндер": "Finder", "калькулятор": "Calculator",
    "capcut": "CapCut", "капкат": "CapCut", "terminal": "Terminal", "терминал": "Terminal",
}


def _osa(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return r.stdout.strip()


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
            if rest and "youtube" in url:
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


def _player() -> str:
    for app in ("Spotify", "Music"):
        try:
            if _osa(f'application "{app}" is running') == "true":
                return app
        except Exception:
            pass
    return "Music"


def music(cmd: str) -> str:
    c = cmd.strip().lower()
    app = _player()
    verbs = {"play": "play", "играй": "play", "включи": "play", "пауза": "pause", "pause": "pause",
             "стоп": "pause", "next": "next track", "дальше": "next track", "следующ": "next track",
             "prev": "previous track", "назад": "previous track", "предыдущ": "previous track",
             "toggle": "playpause"}
    verb = next((v for k, v in verbs.items() if k in c), "playpause")
    _osa(f'tell application "{app}" to {verb}')
    return f"{app}: {verb}"


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


def run(kind: str, arg: str) -> str:
    """Выполнить команду. Возвращает короткое описание для журнала."""
    if sys.platform != "darwin":
        return "команды на компьютере пока только для Mac"
    kind = kind.upper()
    if kind == "ОТКРЫТЬ":
        return open_thing(arg)
    if kind == "МУЗЫКА":
        return music(arg)
    if kind == "ГРОМКОСТЬ":
        return volume(arg)
    raise ValueError(f"не знаю команду {kind}")
