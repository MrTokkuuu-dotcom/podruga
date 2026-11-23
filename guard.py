"""Охрана «глаз и рук»: что ей нельзя делать на экране никогда и о чём сначала спросить Диму.
Пароли, коды и номера карт не печатает вообще. Перед «купить / отправить / удалить …» — вопрос.
Опасные программы (пароли, настройки, терминал) не трогает."""
import re

from intents import norm

MAX_STEPS = 12          # шагов на задачу, дальше — «продолжать?»
MAX_SECONDS = 90        # секунд на задачу, дальше — «продолжать?»
CONFIRM_TIMEOUT = 20    # сколько ждать «да»; молчание = «нет»


class Blocked(Exception):
    """Нельзя совсем. .reason — фраза для него."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class NeedYes(Exception):
    """Можно только после «да». .question — что спросить."""

    def __init__(self, question: str):
        super().__init__(question)
        self.question = question


# начало слова (ru/en) или кусок (ko) — значит, кнопка необратимая
RISKY_STEMS = ("купи", "покуп", "оплат", "заказ", "оформ", "отправ", "удал", "стер", "опублик", "публик",
               "подпис", "перевест", "подтверд", "списат", "пожертв",
               "send", "buy", "purchase", "pay", "order", "checkout", "delete", "remove", "erase", "post",
               "publish", "subscribe", "confirm", "transfer", "donate", "submit")
RISKY_KO = ("구매", "결제", "주문", "삭제", "전송", "보내", "송금", "게시", "구독", "확인")

BLOCKED_BUNDLES = {"com.apple.keychainaccess", "com.apple.systempreferences", "com.apple.Terminal",
                   "com.googlecode.iterm2", "com.apple.Passwords", "com.bitwarden.desktop",
                   "dev.warp.Warp-Stable", "com.mitchellh.ghostty"}
BLOCKED_NAMES = ("keychain", "связка ключей", "системные настройки", "system settings", "system preferences",
                 "terminal", "терминал", "iterm", "1password", "bitwarden", "lastpass", "dashlane", "пароли",
                 "passwords")

# здесь Enter = отправить сообщение
MESSENGERS = {"ru.keepcoder.Telegram", "org.telegram.desktop", "com.kakao.KakaoTalkMac", "com.apple.MobileSMS",
              "com.hnc.Discord", "com.tinyspeck.slackmacgap", "com.apple.mail", "net.whatsapp.WhatsApp",
              "com.facebook.archon", "jp.naver.line.mac"}
MESSENGER_NAMES = ("telegram", "телеграм", "kakaotalk", "messages", "сообщения", "discord", "slack", "mail",
                   "почта", "whatsapp", "messenger", "line")

SECRET_WORDS = re.compile(r"\b(пароль|пароля|паролем|парол\w*|password\w*|passwd|cvc|cvv|비밀번호)\b|비밀번호")
CODE_WITH_DIGITS = re.compile(r"\b(код|code|pin|пин|otp)\b\D{0,12}\d{3,}")
LONG_NUMBER = re.compile(r"(?:\d[\s-]?){12,}")

NAMES = {"аня", "алиса", "таня", "подруга", "подружка", "anya", "alisa", "tanya"}
STOP_WORDS = {"стоп", "хватит", "отмена", "отмени", "отменяй", "подожди", "погоди", "стой", "прекрати",
              "stop", "cancel", "wait", "abort", "그만", "멈춰", "잠깐", "취소"}
YES_WORDS = {"да", "давай", "жми", "нажми", "нажимай", "ага", "угу", "конечно", "можно", "разрешаю", "окей",
             "ок", "yes", "yeah", "yep", "ok", "okay", "sure", "네", "응", "예", "그래", "좋아", "어"}
NO_WORDS = {"нет", "не", "неа", "нельзя", "отмена", "no", "nope", "don", "dont", "아니", "아니야", "안돼", "싫어", "하지마"}


def check_app(app_name: str, bundle_id: str) -> None:
    low = (app_name or "").lower()
    if bundle_id in BLOCKED_BUNDLES or any(n in low for n in BLOCKED_NAMES):
        raise Blocked(f"В «{app_name}» я не лезу — там пароли или настройки Mac. Это лучше сам.")


def check_press(label: str, confirmed: bool = False) -> None:
    if confirmed:
        return
    t = norm(label or "")
    words = t.split()
    if any(w.startswith(RISKY_STEMS) for w in words) or any(k in t for k in RISKY_KO):
        raise NeedYes(f"Нажать «{label.strip()}»?")


def check_key(name: str, app_name: str = "", bundle_id: str = "", confirmed: bool = False) -> None:
    """Enter в мессенджере или почте отправляет сообщение — только после «да»."""
    if confirmed or name != "enter":
        return
    low = (app_name or "").lower()
    if bundle_id in MESSENGERS or any(n == low or low.startswith(n) for n in MESSENGER_NAMES):
        raise NeedYes(f"Отправить сообщение в «{app_name}»?")


def check_type(text: str, secure: bool) -> None:
    if secure:
        raise Blocked("Это поле для пароля — пароли я не ввожу никогда. Введи сам, пожалуйста.")
    t = (text or "").lower()
    if SECRET_WORDS.search(t) or CODE_WITH_DIGITS.search(t) or LONG_NUMBER.search(t):
        raise Blocked("Похоже на пароль, код или номер карты — такое я не печатаю. Введи сам, пожалуйста.")


def _words(text: str) -> list[str]:
    ws = norm(text).replace("-", " - ").split()
    while ws and ws[0] in NAMES:
        ws = ws[1:]
    return ws


def is_stop(text: str) -> bool:
    ws = norm(text).split()           # «стоп-кадр» остаётся одним словом — это не «стоп»
    while ws and ws[0] in NAMES:
        ws = ws[1:]
    return bool(ws) and ws[0] in STOP_WORDS


def yes_no(text: str) -> bool | None:
    ws = _words(text)
    if not ws:
        return None
    if ws[0] in NO_WORDS:
        return False
    if ws[0] in YES_WORDS:
        return True
    return None
