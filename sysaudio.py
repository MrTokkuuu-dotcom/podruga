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




def _get_list(obj: int, selector: str) -> list[int]:
    addr = _Addr(_fourcc(selector), _fourcc("glob"), 0)
    size = ctypes.c_uint32(0)
    if _ca.AudioObjectGetPropertyDataSize(ctypes.c_uint32(obj), ctypes.byref(addr), 0, None, ctypes.byref(size)):
        return []
    n = size.value // 4
    if not n:
        return []
    arr = (ctypes.c_uint32 * n)()
    if _ca.AudioObjectGetPropertyData(ctypes.c_uint32(obj), ctypes.byref(addr), 0, None,
                                      ctypes.byref(size), arr):
        return []
    return list(arr)


MEDIA = ("chrome", "safari", "webkit", "firefox", "arc", "edge", "brave", "whale", "opera", "vivaldi", "yandex",
         "spotify", "music", "vlc", "iina", "quicktime", "tv", "podcasts", "netflix", "infuse", "mpv",
         "youtube", "soundcloud", "tidal", "deezer", "melon", "genie", "flo")


def _app_words(path: str) -> set:
    """«/Applications/Google Chrome.app/…/Google Chrome Helper» → {google, chrome, helper, …}: только имя программы."""
    import re
    m = re.search(r"([^/]+)\.app(?:/|$)", path)
    name = m.group(1) if m else path.rsplit("/", 1)[-1]
    if "com.apple.webkit" in path.lower():
        name += " webkit"
    return set(re.findall(r"[a-z]+", name.lower()))


def _pid_path(pid: int) -> str:
    try:
        buf = ctypes.create_string_buffer(4096)
        lib = ctypes.CDLL(ctypes.util.find_library("proc") or "/usr/lib/libproc.dylib")
        n = lib.proc_pidpath(ctypes.c_int(pid), buf, ctypes.c_uint32(4096))
        return buf.value[:n].decode("utf-8", "ignore") if n > 0 else ""
    except Exception:
        return ""


def players() -> list[str]:
    """Пути программ (кроме самой Подруги), которые сейчас выводят звук. macOS 14+; иначе []."""
    import os
    global _ca
    if sys.platform != "darwin":
        return []
    if _ca is None:
        _ca = ctypes.CDLL(ctypes.util.find_library("CoreAudio"))
    me, out = os.getpid(), []
    for p in _get_list(_SYSTEM, "prs#"):                # kAudioHardwarePropertyProcessObjectList
        pid = _get_u32(p, "ppid")                       # kAudioProcessPropertyPID
        if pid and pid != me and _get_u32(p, "piro"):   # kAudioProcessPropertyIsRunningOutput
            out.append(_pid_path(pid))
    return out


def media_playing() -> bool:
    """Играет браузер или плеер (то, чем управляют ⏯ ⏭). Её голос и программы, которые просто держат
    звук открытым (VRoid Studio, игры), не считаются. Старая macOS — как output_running()."""
    try:
        if _ca is None and sys.platform == "darwin":
            players()
        if sys.platform != "darwin" or not _get_list(_SYSTEM, "prs#"):
            return output_running()
        return any(_app_words(p) & set(MEDIA) for p in players())
    except Exception:
        return output_running()


SILENT = ("vroid",)          # держат звук открытым, даже когда молчат


def others_playing() -> bool:
    """Звук играет какая-то ДРУГАЯ программа: не сама Подруга и не те, что просто держат звук открытым
    (VRoid Studio). macOS 14+; на старых — как output_running()."""
    try:
        if sys.platform != "darwin":
            return False
        ps = players()
        if not ps and not _get_list(_SYSTEM, "prs#"):
            return output_running()
        return any(not (_app_words(p) & set(SILENT)) for p in ps)
    except Exception:
        return output_running()

if __name__ == "__main__":
    print("звук на Mac играет:", output_running(), "| плеер/браузер:", media_playing(), players())
