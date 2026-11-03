"""Автопауза: игра из списка, тяжёлая загрузка видеокарты или горячая клавиша.
На паузе модель выгружается из видеокарты; после — загружается обратно."""
import os
import sys
import threading
import time

import psutil

from gpu import gpu_total_mac, gpu_usage_by_pid
from journal import now

# Эти процессы не считаем «тяжёлой нагрузкой»: рабочий стол Windows и сама модель.
IGNORE_NAMES = {"dwm.exe", "explorer.exe", "csrss.exe"}


class AutoPause:
    def __init__(self, cfg, journal, ollama, on_pause, on_resume):
        a = cfg["autopause"]
        self.games = {g.lower() for g in a["games"]}
        self.gpu_threshold = a["gpu_threshold"]
        self.gpu_seconds = a["gpu_seconds"]
        self.resume_delay = a["resume_delay"]
        self.poll = a["poll_interval"]
        self.journal, self.ollama = journal, ollama
        self.on_pause, self.on_resume = on_pause, on_resume

        self.paused = False
        self.reason = self.detail = self.paused_at = None
        self._high_since = None   # с какого момента видеокарта загружена
        self._clear_since = None  # с какого момента причина паузы пропала
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # --- проверки ---
    def _running_game(self) -> str | None:
        for p in psutil.process_iter(["name"]):
            name = p.info["name"] or ""
            if name.lower() in self.games:
                return name
        return None

    def _external_gpu(self) -> tuple[float, str | None]:
        """Загрузка видеокарты всеми, кроме нас самих, Ollama и рабочего стола."""
        if sys.platform == "darwin":
            # На Mac видна только общая загрузка. В простой версии мозг в облаке,
            # поэтому видеочип грузим не мы — общая цифра подходит.
            return gpu_total_mac(), "тяжёлая программа"
        total, top_name, top_val = 0.0, None, 0.0
        for pid, value in gpu_usage_by_pid().items():
            if pid == os.getpid():
                continue
            try:
                name = psutil.Process(pid).name()
            except psutil.Error:
                continue
            low = name.lower()
            if low in IGNORE_NAMES or "ollama" in low:
                continue
            total += value
            if value > top_val:
                top_name, top_val = name, value
        return min(total, 100.0), top_name

    # --- основной цикл ---
    def check_once(self) -> None:
        with self._lock:
            t = time.monotonic()
            game = self._running_game()

            if not self.paused:
                if game:
                    self._pause("game", game)
                    return
                load, top = self._external_gpu()
                if load >= self.gpu_threshold:
                    self._high_since = self._high_since or t
                    if t - self._high_since >= self.gpu_seconds:
                        self._pause("gpu", top or "неизвестная программа")
                else:
                    self._high_since = None
                return

            if self.reason == "hotkey":
                return  # ручную паузу снимает только клавиша
            busy = bool(game)
            if not busy and self.reason == "gpu":
                busy = self._external_gpu()[0] >= self.gpu_threshold
            if busy:
                self._clear_since = None
            else:
                self._clear_since = self._clear_since or t
                if t - self._clear_since >= self.resume_delay:
                    self._resume()

    def toggle(self) -> None:
        with self._lock:
            if self.paused:
                self._resume()
            else:
                self._pause("hotkey")

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception as e:  # пауза не должна ронять всю программу
                print(f"[автопауза] ошибка: {e}")
            self._stop.wait(self.poll)

    def stop(self) -> None:
        self._stop.set()

    # --- переходы ---
    def _pause(self, reason: str, detail: str | None = None) -> None:
        self.paused, self.reason, self.detail = True, reason, detail
        self.paused_at = now()
        self._high_since = self._clear_since = None
        self.journal.log("pause", reason=reason, detail=detail)
        self.on_pause(reason, detail)  # сначала фраза, потом выгрузка
        self.ollama.unload()

    def _resume(self) -> None:
        away = (now() - self.paused_at).total_seconds()
        reason, detail, since = self.reason, self.detail, self.paused_at
        self.paused, self.reason, self.detail = False, None, None
        self._clear_since = None
        self.ollama.preload()
        self.journal.log("resume", away_sec=int(away), after=reason, detail=detail)
        self.on_resume(reason, detail, away, since)
