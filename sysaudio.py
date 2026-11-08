"""Играет ли сейчас звук на самом Mac (музыка, YouTube, игра). Через CoreAudio, без разрешений:
спрашиваем у устройства вывода, крутит ли его хоть одна программа. Пока Mac сам играет звук,
уши становятся строже, чтобы она не принимала видео и песни за тебя."""
import ctypes
import ctypes.util
import struct
import sys

_ca = None
_SYSTEM = 1                                    # kAudioObjectSystemObject


def _fourcc(s: str) -> int:
    return struct.unpack(">I", s.encode())[0]


class _Addr(ctypes.Structure):
    _fields_ = [("selector", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("element", ctypes.c_uint32)]


def _get_u32(obj: int, selector: str) -> int | None:
    addr = _Addr(_fourcc(selector), _fourcc("glob"), 0)
    val = ctypes.c_uint32(0)
    size = ctypes.c_uint32(4)
    err = _ca.AudioObjectGetPropertyData(ctypes.c_uint32(obj), ctypes.byref(addr), 0, None,
                                         ctypes.byref(size), ctypes.byref(val))
    return None if err else val.value


def output_running() -> bool:
    """True — устройство вывода сейчас кем-то занято (идёт звук). Если узнать нельзя — False."""
    global _ca
    if sys.platform != "darwin":
        return False
    try:
        if _ca is None:
            _ca = ctypes.CDLL(ctypes.util.find_library("CoreAudio"))
        dev = _get_u32(_SYSTEM, "dOut")             # kAudioHardwarePropertyDefaultOutputDevice
        if not dev:
            return False
        return bool(_get_u32(dev, "gone"))          # kAudioDevicePropertyDeviceIsRunningSomewhere
    except Exception:
        return False


if __name__ == "__main__":
    print("звук на Mac играет:", output_running())
