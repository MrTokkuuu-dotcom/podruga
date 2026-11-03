"""Загрузка видеокарты по процессам. Работает и с NVIDIA, и с AMD.
Используем WMI-класс, а не Get-Counter: названия счётчиков на русской/корейской
Windows переведены, и Get-Counter с английским путём там не работает."""
import re
import subprocess
import sys

_PS = (
    "Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine | "
    "Where-Object { $_.UtilizationPercentage -gt 0 } | "
    "ForEach-Object { $_.Name + '|' + $_.UtilizationPercentage }"
)
_RX = re.compile(r"pid_(\d+)_.*engtype_(\w+)", re.IGNORECASE)


def parse(output: str) -> dict[int, float]:
    per_engine: dict[tuple[int, str], float] = {}
    for line in output.splitlines():
        name, _, value = line.strip().rpartition("|")
        m = _RX.search(name)
        if not m:
            continue
        try:
            v = float(value)
        except ValueError:
            continue
        key = (int(m.group(1)), m.group(2).lower())
        per_engine[key] = per_engine.get(key, 0.0) + v
    result: dict[int, float] = {}
    for (pid, _engine), v in per_engine.items():
        result[pid] = max(result.get(pid, 0.0), v)  # самый загруженный движок процесса
    return result


_MAC_RX = re.compile(r'"Device Utilization %"\s*=\s*(\d+)')


def gpu_total_mac() -> float:
    """Общая загрузка видеочипа на Mac (по процессам macOS не показывает)."""
    if sys.platform != "darwin":
        return 0.0
    try:
        out = subprocess.run(["ioreg", "-r", "-d", "1", "-c", "IOAccelerator"],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return 0.0
    values = [float(v) for v in _MAC_RX.findall(out)]
    return max(values) if values else 0.0


def gpu_usage_by_pid() -> dict[int, float]:
    """{pid: % загрузки}. Не на Windows или при ошибке — пустой словарь."""
    if sys.platform != "win32":
        return {}
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", _PS],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout
    except Exception:
        return {}
    return parse(out)
