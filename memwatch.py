"""Сколько памяти свободно у Mac и сколько он выгрузил на диск (swap). Когда тесно — всё тормозит:
ответ мозга вместо 3 с идёт 12–20 с (журнал 29.11.2026, рядом был запущен симулятор iPhone)."""
import re
import subprocess


def snapshot() -> dict:
    """{'free': ГБ свободно (вместе с тем, что Mac отдаст сразу), 'swap': ГБ на диске}. Пусто — не вышло."""
    try:
        vm = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=2).stdout
        page = int(re.search(r"page size of (\d+)", vm).group(1))
        get = lambda k: int(re.search(rf"{k}:\s+(\d+)", vm).group(1))
        free = (get("Pages free") + get("Pages inactive") + get("Pages speculative") + get("Pages purgeable")) * page
        sw = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=2).stdout
        m = re.search(r"used = ([\d.]+)M", sw)
        return {"free": free / 2**30, "swap": float(m.group(1)) / 1024 if m else 0.0}
    except Exception:
        return {}


def line() -> str:
    s = snapshot()
    if not s:
        return ""
    tight = s["free"] < 1.5                     # swap после тесноты держится долго — по нему не судим
    return (f"[память] свободно {s['free']:.1f} ГБ, на диске {s['swap']:.1f} ГБ"
            + (" — ТЕСНО: тяжёлые программы рядом тормозят её ответы" if tight else ""))
