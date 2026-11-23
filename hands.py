"""«Руки»: нажать кнопку, напечатать, нажать клавишу, полистать. Каждое действие сначала проходит
через охрану (guard.py): пароли не печатает, «купить / отправить / удалить» — только после «да».
Нажимает по возможности без мыши (AXPress); если нельзя — кликает мышью в центр, а её собственное
прозрачное окно на это время целиком пропускает мышь, чтобы не нажать по себе."""
import time

import guard

KEYS = {"enter": 36, "tab": 48, "esc": 53, "space": 49, "up": 126, "down": 125, "left": 123, "right": 124,
        "pageup": 116, "pagedown": 121, "cmd+l": 37, "cmd+f": 3}
_overlay = None


def set_overlay_hook(fn) -> None:
    """fn(True) — окно Подруги пропускает мышь целиком; fn(False) — как обычно."""
    global _overlay
    _overlay = fn


# --- низкий уровень (подменяется в проверках) ---
def _ax_press(ref) -> bool:
    if ref is None:
        return False
    from ApplicationServices import AXUIElementPerformAction
    try:
        return AXUIElementPerformAction(ref, "AXPress") == 0
    except Exception:
        return False


def _mouse_click(x: float, y: float) -> None:
    from Quartz import (CGEventCreateMouseEvent, CGEventPost, kCGEventLeftMouseDown, kCGEventLeftMouseUp,
                        kCGHIDEventTap, kCGMouseButtonLeft)
    for kind in (kCGEventLeftMouseDown, kCGEventLeftMouseUp):
        ev = CGEventCreateMouseEvent(None, kind, (x, y), kCGMouseButtonLeft)
        CGEventPost(kCGHIDEventTap, ev)
        time.sleep(0.05)


def _type_unicode(text: str) -> None:
    from Quartz import CGEventCreateKeyboardEvent, CGEventKeyboardSetUnicodeString, CGEventPost, kCGHIDEventTap
    for i in range(0, len(text), 20):
        chunk = text[i:i + 20]
        for down in (True, False):
            ev = CGEventCreateKeyboardEvent(None, 0, down)
            CGEventKeyboardSetUnicodeString(ev, len(chunk), chunk)
            CGEventPost(kCGHIDEventTap, ev)
        time.sleep(0.03)


def _post_key(name: str) -> None:
    from Quartz import (CGEventCreateKeyboardEvent, CGEventPost, CGEventSetFlags, kCGEventFlagMaskCommand,
                        kCGHIDEventTap)
    code = KEYS[name]
    for down in (True, False):
        ev = CGEventCreateKeyboardEvent(None, code, down)
        if name.startswith("cmd+"):
            CGEventSetFlags(ev, kCGEventFlagMaskCommand)
        CGEventPost(kCGHIDEventTap, ev)
        time.sleep(0.03)


def _scroll(dy: int) -> None:
    from Quartz import CGEventCreateScrollWheelEvent, CGEventPost, kCGHIDEventTap, kCGScrollEventUnitLine
    CGEventPost(kCGHIDEventTap, CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitLine, 1, dy))


def _focus(el) -> None:
    from ApplicationServices import AXUIElementSetAttributeValue
    if el.ref is not None:
        try:
            if AXUIElementSetAttributeValue(el.ref, "AXFocused", True) == 0:
                time.sleep(0.1)
                return
        except Exception:
            pass
    _click_center(el)
    time.sleep(0.15)


def _click_center(el) -> None:
    x, y = el.center
    if _overlay:
        _overlay(True)
    try:
        _mouse_click(x, y)
    finally:
        if _overlay:
            _overlay(False)


# --- действия ---
def press(el, app: str, bundle_id: str, confirmed: bool = False) -> str:
    guard.check_app(app, bundle_id)
    guard.check_press(el.label, confirmed)
    if not _ax_press(el.ref):
        _click_center(el)
        return f"кликнула «{el.label}»"
    return f"нажала «{el.label}»"


def type_text(el, text: str, app: str, bundle_id: str, enter: bool = False, confirmed: bool = False) -> str:
    guard.check_app(app, bundle_id)
    guard.check_type(text, el.secure)
    if enter:
        guard.check_key("enter", app, bundle_id, confirmed)
    _focus(el)
    _type_unicode(text)
    if enter:
        _post_key("enter")
    return f"напечатала «{text}» в «{el.label}»" + (" и Enter" if enter else "")


def key(name: str, app: str = "", bundle_id: str = "", confirmed: bool = False) -> str:
    name = name.strip().lower()
    if name not in KEYS:
        raise ValueError(f"такую клавишу не жму: {name}")
    if app or bundle_id:
        guard.check_app(app, bundle_id)
    guard.check_key(name, app, bundle_id, confirmed)
    _post_key(name)
    return f"клавиша {name}"


def scroll(direction: str) -> str:
    down = "вниз" in direction or "down" in direction
    _scroll(-8 if down else 8)
    return "листаю вниз" if down else "листаю вверх"
