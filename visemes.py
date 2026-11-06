"""Форма рта по звуку: по формантам (LPC) кусочка речи угадываем гласную — а / о / у / и / э.
Грубо, но рот перестаёт просто «хлопать», а складывается по-разному."""
import numpy as np

RATE = 24000
# (F1, F2) для женского голоса, Гц
PROTO = {"aa": (850, 1400), "oh": (560, 950), "ou": (380, 800), "ih": (320, 2400), "ee": (520, 2050)}
_last = "aa"


def _lpc(x: np.ndarray, order: int) -> np.ndarray:
    r = np.correlate(x, x, "full")[len(x) - 1:len(x) + order]
    a = np.zeros(order + 1); a[0] = 1.0
    e = r[0] + 1e-9
    for i in range(1, order + 1):
        k = -(r[i] + np.dot(a[1:i], r[i - 1:0:-1])) / e
        a[1:i + 1] = a[1:i + 1] + k * a[i - 1::-1][:i]
        e *= (1 - k * k)
        if e <= 0:
            break
    return a


def formants(piece: np.ndarray, rate: int = RATE):
    x = piece.astype(np.float64)
    step = max(1, rate // 8000)
    x = x[: len(x) // step * step].reshape(-1, step).mean(axis=1)    # ~8 кГц
    fs = rate / step
    x = np.append(x[0], x[1:] - 0.94 * x[:-1]) * np.hamming(len(x))
    a = _lpc(x, 10)
    roots = [z for z in np.roots(a) if np.imag(z) > 0.01]
    fr = sorted((np.angle(z) * fs / (2 * np.pi), -np.log(abs(z)) * fs / np.pi) for z in roots)
    fr = [f for f, bw in fr if 200 < f < 3500 and bw < 500]
    return fr[:2] if len(fr) >= 2 else None


def shape(piece: np.ndarray, rate: int = RATE) -> str:
    """'aa' | 'oh' | 'ou' | 'ih' | 'ee'; для тихих и шипящих кусочков — прошлая форма."""
    global _last
    if len(piece) < 400 or np.sqrt(np.mean(piece.astype(np.float32) ** 2)) < 300:
        return _last
    try:
        f = formants(piece, rate)
    except Exception:
        return _last
    if not f:
        return _last
    f1, f2 = f
    _last = min(PROTO, key=lambda k: ((f1 - PROTO[k][0]) / 250) ** 2 + ((f2 - PROTO[k][1]) / 600) ** 2)
    return _last
