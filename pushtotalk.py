"""Клавиша микрофона: работает как кнопка 🎙 рядом с ней (нажал — слушает, нажал ещё раз — закончил, или «держать»).
Удобно, когда она гуляет по экрану и до кнопки не дотянуться. Какая клавиша — в настройках («microphone.ptt_key»).
Ловим средствами macOS (NSEvent, только клавиши-модификаторы: они не печатают букв в других программах),
нужен «Универсальный доступ» — он у неё уже есть для «рук»."""
import sys

# имя → (код клавиши, бит в modifierFlags, подпись)
KEYS = {
    "ralt": (61, 0x40, "⌥ справа"),
    "rcmd": (54, 0x10, "⌘ справа"),
    "rshift": (60, 0x04, "⇧ справа"),
    "rctrl": (62, 0x2000, "⌃ справа"),
    "fn": (63, 1 << 23, "fn / 🌐"),
    "off": (None, 0, "выключена"),
}
_keep = []


def label(name: str) -> str:
    return KEYS.get(name, KEYS["ralt"])[2]


def start(on_press, on_release, key_name=lambda: "ralt") -> bool:
    """key_name() спрашивается на каждое нажатие — смена в настройках действует сразу, без перезапуска."""
    if sys.platform != "darwin":
        return False
    try:
        from PyObjCTools import AppHelper
        AppHelper.callAfter(_install, on_press, on_release, key_name)     # мониторы — только в главном потоке
        return True
    except Exception as e:
        print(f"[кнопка] не включилась: {e}")
        return False


def _install(on_press, on_release, key_name):
    from AppKit import NSEvent
    state = {"down": False}
    MASK = 1 << 12                # NSEventMaskFlagsChanged

    def handle(ev):
        try:
            code, bit, _ = KEYS.get(key_name(), KEYS["ralt"])
            if code is None or ev.keyCode() != code:
                return
            down = bool(ev.modifierFlags() & bit)
            if down != state["down"]:
                state["down"] = down
                (on_press if down else on_release)()
        except Exception as e:
            print(f"[кнопка] {e}")

    def local(ev):
        handle(ev)
        return ev

    _keep.append(NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(MASK, handle))   # в других программах
    _keep.append(NSEvent.addLocalMonitorForEventsMatchingMask_handler_(MASK, local))     # в её окне
    print(f"[кнопка] клавиша микрофона: {label(key_name())}")
