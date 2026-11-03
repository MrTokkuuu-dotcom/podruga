"""Горячая клавиша паузы. Windows — библиотека keyboard, Mac — pynput.
На Mac нужно разрешение: Системные настройки → Конфиденциальность и безопасность →
Универсальный доступ и Мониторинг ввода → включить Терминал."""
import sys


def _to_pynput(combo: str) -> str:
    keys = []
    for k in combo.lower().split("+"):
        k = k.strip()
        keys.append(f"<{k}>" if k in {"ctrl", "alt", "shift", "cmd", "option"} else k)
    return "+".join(keys).replace("<option>", "<alt>")


def register(cfg_autopause: dict, callback) -> str:
    """Включает клавишу и возвращает её название для вывода в консоль."""
    if sys.platform == "darwin":
        from pynput import keyboard as kb
        combo = cfg_autopause.get("hotkey_mac")
        if not combo:
            return "выключена (пауза — кнопкой в окне)"
        listener = kb.GlobalHotKeys({_to_pynput(combo): callback})
        listener.daemon = True
        listener.start()
        return combo
    import keyboard
    combo = cfg_autopause["hotkey"]
    keyboard.add_hotkey(combo, callback)
    return combo
