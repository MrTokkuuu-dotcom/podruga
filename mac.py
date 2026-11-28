"""Сам Mac по голосу: кнопки ⏯ ⏭ ⏮ (как на клавиатуре — управляют тем, что сейчас играет, в том числе
YouTube Music и YouTube в браузере), закрыть программу, скриншот, папки, найти файл.
Ничего не удаляет. Закрыть программу — только после «да» (там может быть несохранённое)."""
import re
import subprocess
import sys
import time
from pathlib import Path

PLAY, NEXT, PREV = 16, 17, 18          # NX_KEYTYPE_PLAY / NEXT / PREVIOUS
_last_media = 0.0                      # когда последний раз что-то включали мы (рецептом) или кнопкой ⏯
MEDIA_FRESH = 3 * 3600                 # столько секунд считаем, что «то, что играло», ещё помнит ⏯


class Nothing(RuntimeError):
    """Сделать нечего — текст для него вслух («сейчас ничего не играет»)."""


def note_media() -> None:
    """Включили что-то сами (рецепт YouTube Music / YouTube) — теперь ⏯ знает, чем управлять."""
    global _last_media
    _last_media = time.time()


# --- низкий уровень (подменяется в проверках) ---
def _osa(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return r.stdout.strip()


def _media_key(code: int) -> None:
    """Нажать «мультимедийную» кнопку — как F7/F8/F9 на клавиатуре Mac."""
    from AppKit import NSEvent
    from Quartz import CGEventPost, kCGHIDEventTap
    for down in (True, False):
        state = 0xA if down else 0xB
        ev = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            14, (0, 0), state << 8, 0, 0, None, 8, (code << 16) | (state << 8), -1)
        CGEventPost(kCGHIDEventTap, ev.CGEvent())
        time.sleep(0.03)


def _can_post() -> bool:
    """Нажимать кнопки за него macOS разрешает только с «Универсальным доступом»."""
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def _app_state(app: str) -> str | None:
    """'playing' | 'paused' | 'stopped' — если Spotify / «Музыка» запущены; None — не запущены."""
    try:
        if _osa(f'application "{app}" is running') != "true":
            return None
        return _osa(f'tell application "{app}" to player state as string') or "stopped"
    except Exception:
        return None


def _sound() -> bool:
    try:
        import sysaudio
        return sysaudio.media_playing()            # браузер/плеер; её голос и VRoid не считаются
    except Exception:
        return False


# --- музыка ---
VERBS = {"play": "play", "pause": "pause", "next": "next track", "prev": "previous track"}


def music(cmd: str, sound: bool | None = None) -> str:
    """cmd: play | pause | next | prev. sound — играл ли звук ДО того, как она заговорила
    (её собственный голос тоже занимает динамики, поэтому спрашиваем заранее)."""
    c = cmd.strip().lower()
    kind = next((k for k in VERBS if c.startswith(k)), None)
    if kind is None:
        kind = {"следующ": "next", "дальше": "next", "предыдущ": "prev", "назад": "prev", "пауза": "pause",
                "стоп": "pause"}.get(next((k for k in ("следующ", "дальше", "предыдущ", "назад", "пауза", "стоп")
                                           if k in c), ""), "play")
    if sound is None:
        sound = _sound()
    apps = {a: _app_state(a) for a in ("Spotify", "Music")}
    playing = next((a for a, s in apps.items() if s == "playing"), None)
    if playing:                                        # Spotify или «Музыка» сами играют — им и командуем
        _osa(f'tell application "{playing}" to {VERBS[kind]}')
        return f"{playing}: {VERBS[kind]}"
    fresh = time.time() - _last_media < MEDIA_FRESH
    if kind == "play" and sound:
        return "уже играет"                            # ⏯ сейчас бы, наоборот, поставил на паузу
    if (sound or fresh) and _can_post():               # играет браузер (YouTube Music) или недавно играл
        _media_key({"play": PLAY, "pause": PLAY, "next": NEXT, "prev": PREV}[kind])
        if kind in ("play", "pause"):
            note_media()
        return f"кнопка {kind}"
    paused = next((a for a, s in apps.items() if s in ("paused", "stopped")), None)
    if paused and kind != "pause":                     # Spotify открыт, но на паузе
        _osa(f'tell application "{paused}" to {VERBS[kind]}')
        return f"{paused}: {VERBS[kind]}"
    if kind == "pause":
        raise Nothing("Сейчас ничего не играет.")
    if kind == "play":
        raise Nothing("Скажи, что включить. Например: «включи Кино в ютуб музыке».")
    raise Nothing("Сейчас ничего не играет — нечего переключать.")


# --- программы ---
PROTECTED = {"Finder", "Подруга", "Podruga", "loginwindow", "Dock", "SystemUIServer"}


def running_apps() -> list[str]:
    try:
        from AppKit import NSWorkspace
        return [str(a.localizedName()) for a in NSWorkspace.sharedWorkspace().runningApplications()
                if a.activationPolicy() == 0 and a.localizedName()]
    except Exception:
        return []


def find_running(name: str) -> str | None:
    """«телеграм» → «Telegram», если запущен. Сначала по словарю actions.APPS, потом по буквам."""
    import actions
    low = name.strip().lower()
    want = next((app for k, app in actions.APPS.items() if k in low), None)
    apps = running_apps()
    if want:
        return next((a for a in apps if a.lower() == want.lower()), None)
    return next((a for a in apps if low and (low in a.lower() or a.lower() in low)), None)


def quit_app(app: str) -> str:
    if app in PROTECTED:
        raise Nothing(f"{app} я не закрываю.")
    _osa(f'tell application "{app}" to quit')
    return f"закрыла {app}"


# --- снимок, папки, файлы ---
def screenshot() -> Path:
    """Снимок экрана на Рабочий стол, как ⇧⌘3: «Снимок экрана 2026-11-28 в 14.03.12.png».
    В первый раз macOS спросит, можно ли Подруге на Рабочий стол (ждём не дольше 15 с)."""
    desk = Path.home() / "Desktop"
    name = time.strftime("Снимок экрана %Y-%m-%d в %H.%M.%S.png")
    out = desk / name
    subprocess.run(["screencapture", "-x", str(out)], check=True, timeout=15)
    return out


FOLDERS = {"загрузк": "Downloads", "download": "Downloads", "рабоч": "Desktop", "desktop": "Desktop",
           "документ": "Documents", "document": "Documents", "картинк": "Pictures", "фото": "Pictures",
           "изображен": "Pictures", "фотк": "Pictures", "фоток": "Pictures", "музык": "Music", "видео": "Movies",
           "фильм": "Movies", "программ": "/Applications", "applications": "/Applications",
           "다운로드": "Downloads", "바탕화면": "Desktop", "문서": "Documents", "사진": "Pictures"}


def folder_for(text: str) -> Path | None:
    low = text.lower()
    for k, d in FOLDERS.items():
        if k in low:
            return Path(d) if d.startswith("/") else Path.home() / d
    return None


def _ws_open(p: Path, reveal: bool = False) -> None:
    """Открыть через Finder (LaunchServices). Сама папку не читаем — поэтому macOS не спрашивает
    «разрешить доступ к Загрузкам?» (команда `open` из её процесса спрашивала и ждала ответа)."""
    import threading
    from AppKit import NSWorkspace
    from Foundation import NSURL
    url = NSURL.fileURLWithPath_(str(p))
    ws = NSWorkspace.sharedWorkspace()
    box = {}

    def run():
        box["ok"] = True if reveal else bool(ws.openURL_(url))
        if reveal:
            ws.activateFileViewerSelectingURLs_([url])
    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(8)
    if th.is_alive():          # macOS показал окошко «разрешить доступ?» и ждёт его — не висим вместе с ним
        raise Nothing("macOS спрашивает разрешение — нажми «Разрешить» в окошке, и скажи ещё раз.")
    if not box.get("ok"):
        raise RuntimeError(f"не открылось: {p}")


def open_folder(p: Path) -> str:
    _ws_open(p)
    return f"открыла {p.name}"


def find_files(query: str, limit: int = 5) -> list[Path]:
    """Spotlight по имени файла в домашней папке (без системных и скрытых)."""
    q = query.strip().strip("«»\"'")
    if not q:
        return []
    q = re.sub(r"[\"\\]", " ", q)
    try:
        r = subprocess.run(["mdfind", "-onlyin", str(Path.home()), f'kMDItemDisplayName == "*{q}*"cd'],
                           capture_output=True, text=True, timeout=10)
    except Exception:
        return []
    out = []
    for line in r.stdout.splitlines():           # файлы сами не трогаем (stat) — иначе macOS спросит доступ к папкам
        p = Path(line)
        parts = p.relative_to(Path.home()).parts if p.is_relative_to(Path.home()) else p.parts
        if any(s.startswith(".") or s == "Library" for s in parts):
            continue
        if any(s in ("Podruga", "venv", "node_modules", "site-packages") for s in parts):
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def reveal(p: Path) -> str:
    _ws_open(p, reveal=True)
    return f"показала {p.name}"


if __name__ == "__main__" and sys.platform == "darwin":
    print(running_apps())
    print(find_files(" ".join(sys.argv[1:]) or "договор"))
