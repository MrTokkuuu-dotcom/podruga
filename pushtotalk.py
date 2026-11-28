"""«Нажми и говори»: пока зажат правый ⌥ (Option), она слушает; отпустил — отвечает. В этом режиме
не слышит ни видео, ни друзей, ни телевизор — только то, что сказано с зажатой клавишей.
Ловим клавишу средствами macOS (NSEvent), нужен «Универсальный доступ» — он у неё уже есть для «рук»."""
import sys

RIGHT_OPTION = 61                 # код клавиши правого ⌥
_DEV_RALT = 0x40                  # бит «правый Alt/Option» в modifierFlags
_keep = []


def start(on_press, on_release) -> bool:
    if sys.platform != "darwin":
        return False
    try:
        from PyObjCTools import AppHelper
        AppHelper.callAfter(_install, on_press, on_release)     # мониторы ставятся только в главном потоке
        return True
    except Exception as e:
        print(f"[кнопка] не включилась: {e}")
        return False


def _install(on_press, on_release):
    from AppKit import NSEvent
    state = {"down": False}
    MASK = 1 << 12                # NSEventMaskFlagsChanged

    def handle(ev):
        try:
            if ev.keyCode() != RIGHT_OPTION:
                return
            down = bool(ev.modifierFlags() & _DEV_RALT)
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
    print("[кнопка] «нажми и говори»: правый ⌥ (Option)")
