"""Что ты сейчас делаешь — по названию активного приложения (без скриншотов и без
чтения окон). Даёт ей контекст: «он уже час в CapCut». Только названия программ."""
import sys
import threading
import time

IGNORE = {"Подруга", "Python", "python", "loginwindow", "ScreenSaverEngine"}
NICE = {"CapCut": "монтирует видео в CapCut", "Final Cut Pro": "монтирует видео в Final Cut",
        "Premiere Pro": "монтирует видео", "DaVinci Resolve": "монтирует видео",
        "Telegram": "переписывается в Telegram", "KakaoTalk": "переписывается в KakaoTalk",
        "Safari": "в браузере", "Google Chrome": "в браузере", "Arc": "в браузере",
        "Music": "слушает музыку", "Spotify": "слушает музыку", "Steam": "в Steam",
        "Microsoft Word": "работает с документом", "Microsoft Excel": "работает с таблицей",
        "Pages": "пишет документ", "Keynote": "делает презентацию", "Xcode": "программирует",
        "Visual Studio Code": "программирует", "Terminal": "в Терминале", "Терминал": "в Терминале",
        "Finder": "в Finder", "Zoom": "на созвоне в Zoom", "Discord": "в Discord"}


class Activity:
    def __init__(self):
        self.app = None
        self.since = time.monotonic()

    def _front(self) -> str | None:
        from AppKit import NSWorkspace
        a = NSWorkspace.sharedWorkspace().frontmostApplication()
        return str(a.localizedName()) if a else None

    def _loop(self):
        while True:
            try:
                name = self._front()
                if name and name not in IGNORE and name != self.app:
                    self.app, self.since = name, time.monotonic()
            except Exception:
                pass
            time.sleep(5)

    def start(self):
        if sys.platform == "darwin":
            threading.Thread(target=self._loop, name="activity", daemon=True).start()

    def describe(self) -> str | None:
        if not self.app:
            return None
        mins = int((time.monotonic() - self.since) // 60)
        if mins < 2:
            return None
        what = NICE.get(self.app, f"в программе {self.app}")
        dur = f"{mins} мин" if mins < 60 else f"{mins // 60} ч {mins % 60} мин"
        return f"Сейчас он {what} (уже {dur})."
