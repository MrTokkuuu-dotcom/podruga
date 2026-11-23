"""Охрана «глаз и рук». Запуск: ~/Podruga/venv/bin/python devtools/test_guard.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import guard  # noqa: E402
from guard import Blocked, NeedYes  # noqa: E402

bad = []


def expect(exc, fn, *a, **k):
    try:
        fn(*a, **k)
    except Exception as e:
        if exc is None or not isinstance(e, exc):
            bad.append(f"{fn.__name__}{a}{k}: ждал {exc}, получил {type(e).__name__}: {e}")
        return e
    if exc is not None:
        bad.append(f"{fn.__name__}{a}{k}: ждал {exc.__name__}, а прошло")
    return None


RISKY = ["Купить сейчас", "Оформить заказ", "Отправить", "Send", "Delete", "Оплатить", "Опубликовать",
         "Subscribe", "결제하기", "삭제", "전송", "Buy now", "Checkout", "Удалить навсегда", "Подтвердить"]
SAFE = ["Play", "Воспроизвести", "Поиск", "Далее", "Shuffle", "재생", "Главная", "Search", "Открыть"]
for lab in RISKY:
    e = expect(NeedYes, guard.check_press, lab)
    if e is not None and isinstance(e, NeedYes) and lab not in e.question:
        bad.append(f"вопрос без подписи: {e.question}")
    expect(None, guard.check_press, lab, confirmed=True)
for lab in SAFE:
    expect(None, guard.check_press, lab)

expect(Blocked, guard.check_type, "hunter2", secure=True)
for t in ["мой пароль qwerty", "4111 1111 1111 1111", "код 123456", "CVC 123", "password: abc",
          "비밀번호 1234", "pin 0000", "4111-1111-1111-1111"]:
    expect(Blocked, guard.check_type, t, secure=False)
for t in ["виктор цой кино", "погода в пусане", "2024", "blackpink", "아이유", "рецепт рамена"]:
    expect(None, guard.check_type, t, secure=False)

for app, bid in [("Keychain Access", "com.apple.keychainaccess"), ("Связка ключей", "com.apple.keychainaccess"),
                 ("Системные настройки", "com.apple.systempreferences"), ("System Settings", "com.apple.systempreferences"),
                 ("Terminal", "com.apple.Terminal"), ("iTerm2", "com.googlecode.iterm2"),
                 ("1Password", "com.1password.1password"), ("Bitwarden", "com.bitwarden.desktop"),
                 ("Пароли", "com.apple.Passwords")]:
    expect(Blocked, guard.check_app, app, bid)
for app, bid in [("Google Chrome", "com.google.Chrome"), ("Safari", "com.apple.Safari"), ("Music", "com.apple.Music")]:
    expect(None, guard.check_app, app, bid)

for t in ["стоп", "Стоп!", "хватит", "отмена", "подожди", "stop", "cancel", "그만", "멈춰", "Аня, стоп!",
          "подруга хватит", "стоп стоп", "Stop it"]:
    if not guard.is_stop(t):
        bad.append(f"is_stop({t!r}) должно быть True")
for t in ["не останавливайся", "как дела", "я подожду тебя дома", "включи стоп-кадр потом", "", "давай"]:
    if guard.is_stop(t):
        bad.append(f"is_stop({t!r}) должно быть False")

for t, want in [("да", True), ("Да!", True), ("давай", True), ("жми", True), ("ага", True), ("yes", True),
                ("네", True), ("응", True), ("да, нажимай", True), ("конечно", True),
                ("нет", False), ("не надо", False), ("no", False), ("아니", False), ("нет, не жми", False),
                ("не нажимай", False),
                ("что?", None), ("подумаю", None), ("", None), ("а что это", None)]:
    got = guard.yes_no(t)
    if got is not want:
        bad.append(f"yes_no({t!r}) = {got}, ждал {want}")

expect(NeedYes, guard.check_key, "enter", "Telegram", "ru.keepcoder.Telegram")
expect(NeedYes, guard.check_key, "enter", "KakaoTalk", "")
expect(None, guard.check_key, "enter", "Telegram", "ru.keepcoder.Telegram", confirmed=True)
expect(None, guard.check_key, "enter", "Google Chrome", "com.google.Chrome")
expect(None, guard.check_key, "tab", "Telegram", "ru.keepcoder.Telegram")

assert guard.MAX_STEPS == 12 and guard.MAX_SECONDS == 90 and guard.CONFIRM_TIMEOUT == 20

if bad:
    print("\n".join(bad))
    sys.exit(1)
print("OK")
