"""Значок в строке меню (вверху экрана) + автозапуск вместе с Mac.
Меню: показать/спрятать, переписка, уснуть/проснуться, пауза, настройки, автозапуск, выйти."""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

AGENT = Path.home() / "Library" / "LaunchAgents" / "com.podruga.companion.plist"


def bundle_path() -> str:
    return os.environ.get("PODRUGA_APP", "/Applications/Подруга.app")


def autostart_enabled() -> bool:
    return AGENT.exists()


def set_autostart(on: bool) -> bool:
    """Пункт входа через LaunchAgent: при входе в систему просто делает `open` приложения."""
    try:
        if on:
            AGENT.parent.mkdir(parents=True, exist_ok=True)
            with open(AGENT, "wb") as f:
                plistlib.dump({"Label": "com.podruga.companion",
                               "ProgramArguments": ["/usr/bin/open", "-g", bundle_path()],
                               "RunAtLoad": True, "LimitLoadToSessionType": "Aqua"}, f)
        elif AGENT.exists():
            AGENT.unlink()
        return True
    except Exception as e:
        print(f"[меню] автозапуск: {e}")
        return False


def start(companion) -> None:
    if sys.platform != "darwin" or not hasattr(companion.ui, "window"):
        return
    try:
        from PyObjCTools import AppHelper
        AppHelper.callAfter(_build, companion)       # строка меню создаётся только в главном потоке
    except Exception as e:
        print(f"[меню] значок не создан: {e}")


_keep = []      # чтобы сборщик мусора не убрал значок
_companion = None
_Target = None


def _target_class():
    global _Target
    if _Target is not None:
        return _Target
    import threading
    from Foundation import NSObject

    class PodrugaMenuTarget(NSObject):
        def act_(self, item):
            c = _companion
            ui = c.ui
            tag = item.tag()
            bg = lambda f: threading.Thread(target=f, daemon=True).start()
            if tag == 1:
                ui.toggle_visible()
            elif tag == 2:
                ui.ensure_visible()
                ui.show_chat()
            elif tag == 3:
                bg(c.toggle_sleep)
            elif tag == 4:
                bg(c.pauser.toggle)
            elif tag == 5:
                ui.ensure_visible()
                ui.open_settings()
            elif tag == 6:
                set_autostart(not autostart_enabled())
            elif tag == 8:
                bg(lambda: c.set_guests(not c.guests_on()))
            elif tag == 7 and getattr(c, "walker", None):
                c.walker.enabled = not c.walker.enabled
                if not c.walker.enabled:
                    c.walker.stop()
                from config import save_user_settings
                try:
                    save_user_settings(c.cfg, {"walk": "1" if c.walker.enabled else "0"})
                except Exception:
                    pass
            elif tag == 9:
                ui.close()

        def menuWillOpen_(self, menu):
            c = _companion
            menu.itemWithTag_(1).setTitle_("Спрятать" if c.ui.visible else "Показать")
            menu.itemWithTag_(3).setTitle_("Уснуть" if c.awake else "Разбудить")
            menu.itemWithTag_(4).setTitle_("Снять паузу" if c.pauser.paused else "Пауза")
            menu.itemWithTag_(6).setState_(1 if autostart_enabled() else 0)
            menu.itemWithTag_(8).setState_(1 if c.guests_on() else 0)
            w = getattr(c, "walker", None)
            menu.itemWithTag_(7).setState_(1 if (w and w.enabled) else 0)

    _Target = PodrugaMenuTarget
    return _Target


def _build(companion):
    global _companion
    from AppKit import NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength
    _companion = companion
    target = _target_class().alloc().init()
    item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
    item.button().setTitle_("🌸")
    item.button().setToolTip_(companion.cfg.get("companion_name", "Подруга"))
    menu = NSMenu.alloc().init()
    menu.setAutoenablesItems_(False)
    for tag, title in [(1, "Спрятать"), (2, "Переписка"), (3, "Уснуть"), (4, "Пауза"),
                       (5, "Настройки…"), (0, None), (8, "Гости — отвечать только по имени"), (7, "Гулять по экрану"), (6, "Запускать вместе с Mac"),
                       (0, None), (9, "Выйти")]:
        if title is None:
            menu.addItem_(NSMenuItem.separatorItem())
            continue
        mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "act:", "")
        mi.setTarget_(target)
        mi.setTag_(tag)
        menu.addItem_(mi)
    menu.setDelegate_(target)
    item.setMenu_(menu)
    _keep.extend([item, menu, target])
    global _menu
    _menu = menu
    print("[меню] значок в строке меню готов")


_menu = None


def popup() -> None:
    """То же меню по правому клику на неё (если значок спрятался за «чёлкой» экрана)."""
    if _menu is None:
        return
    from PyObjCTools import AppHelper

    def show():
        from AppKit import NSEvent
        _menu.delegate().menuWillOpen_(_menu)
        _menu.popUpMenuPositioningItem_atLocation_inView_(None, NSEvent.mouseLocation(), None)
    AppHelper.callAfter(show)
