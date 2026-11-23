"""Живая проверка «глаз»: что она видит в активном окне.
Запуск: ~/Podruga/venv/bin/python devtools/eyes_live.py [секунд_подождать] [--ocr]
За это время переключись на нужное окно (например, YouTube Music в браузере)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import eyes  # noqa: E402

wait = float(next((a for a in sys.argv[1:] if not a.startswith("--")), 3))
print("разрешения:", eyes.permissions())
time.sleep(wait)
t = time.monotonic()
snap = eyes.snapshot()
print(f"снимок за {time.monotonic() - t:.2f} с, элементов {len(snap.elements)}, текстов {len(snap.texts)}")
print(eyes.format_for_brain(snap))
if "--ocr" in sys.argv:
    t = time.monotonic()
    found = eyes.read_text()
    print(f"\nраспознано за {time.monotonic() - t:.2f} с: {len(found)} строк")
    for s, fr in found[:40]:
        print(f"  {s}  @{tuple(round(v) for v in fr)}")
