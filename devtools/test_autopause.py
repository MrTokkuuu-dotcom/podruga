"""Автопауза не пугается собственной работы Подруги (мозг и голос на видеочипе).
Запуск: ~/Podruga/venv/bin/python devtools/test_autopause.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import autopause  # noqa: E402
import gpu  # noqa: E402

CFG = {"autopause": {"games": [], "gpu_threshold": 70, "gpu_seconds": 30, "resume_delay": 5, "poll_interval": 2}}


class J:
    def log(self, *a, **k): pass


class M:
    def unload(self): return True
    def preload(self): return True


clock = [1000.0]
autopause.time.monotonic = lambda: clock[0]
gpu.time.monotonic = lambda: clock[0]
autopause.sys.platform = "darwin"
autopause.gpu_total_mac = lambda: 95.0          # видеочип загружен на 95 %
paused = []
ap = autopause.AutoPause(CFG, J(), M(), lambda r, d: paused.append(r), lambda *a: None)
ap._running_game = lambda: None

# Подруга сама думает и говорит каждые 10 с — 2 минуты подряд: паузы нет
for i in range(60):
    if i % 5 == 0:
        gpu.mark_own()
    ap.check_once(); clock[0] += 2
assert not paused, f"своя работа не должна ставить на паузу: {paused}"

# она молчит, а видеочип всё равно занят 40 с (игра, видеомонтаж) — пауза
for _ in range(25):
    ap.check_once(); clock[0] += 2
assert paused == ["gpu"], paused
print("OK")
