"""ИИ-компаньон «Подруга»: слышит, отвечает живым голосом, помнит, видит экран по просьбе.
«Привет, подруга» — просыпается. «Посмотри / глянь» — смотрит на экран. «Спокойной ночи» — засыпает.
Запуск: python main.py   (или python main.py --text — без микрофона и окна, для проверки)"""
import bootstrap

bootstrap.check_update()  # новый код с GitHub (если настроен update.json)
bootstrap.ensure_deps()   # до тяжёлых импортов: при обновлении сама доставит библиотеки

import os  # noqa: E402
import random
import signal
import sys
import threading
import time
from collections import deque

import logsetup
from autopause import AutoPause
from brain import FORMAT_RULES, GeminiBrain, NullModel
from config import (HOME, ROOT, has_key, load_config, save_key, save_user_settings)
from journal import Journal, LastSeen, now
from memory import Memory, extract_facts
from reply_parser import ReplyParser
from ui import NullUI, make_ui
from wake import is_goodbye
from wake_context import build_wake_context

PAUSE_LINES = {
    "game": "Окей, иди играй, я тут подожду!",
    "gpu": "Вижу, компьютер занят. Не буду мешать.",
    "hotkey": "Ладно, молчу. Нажми ещё раз, когда захочешь.",
}
LOOK_TEXT = "Посмотри на мой экран и коротко скажи, что видишь."


class Companion:
    def __init__(self, cfg: dict, text_mode: bool = False):
        self.cfg = cfg
        data = cfg["_data_dir"]
        self.journal = Journal(data / "journal.jsonl", cfg["user_name"])
        self.memory = Memory(data, cfg["backup_keep_days"])
        self.memory.backup_daily()
        self.last_seen = LastSeen(data / "last_seen.txt")

        self.brain = None                 # создаётся, когда есть ключ
        self.history: deque[dict] = deque(maxlen=cfg["brain"]["history_turns"] * 2)
        self.unsaved: list[str] = []
        self.last_talk = time.monotonic()
        self.last_awake_at = None
        self.busy = threading.Lock()
        self.last_parser = None
        self.barge = False                # перебивание (только в наушниках)
        self.speaking = False
        self._cancel = False
        self._work_t = None               # «чёрный ящик»: когда начался текущий ответ
        self.ready = threading.Event()    # мозг и голос готовы
        self._level_t = 0.0

        self.text_mode = text_mode
        self.ui = NullUI() if text_mode else make_ui(cfg)
        if self.ui.enabled:
            self.ui.api._companion = self
        self.listener = None
        self.speaker = _PrintSpeaker() if text_mode else None

        self.wake = None
        self.awake = True
        w = cfg.get("wake", {})
        if not text_mode and w.get("enabled"):
            try:
                from wake import WakeWord
                self.wake = WakeWord(str(ROOT / w["model_dir"]), w["phrases"], w["sleep_phrases"])
                self.awake = False
            except Exception as e:
                print(f"⚠ Голосовые команды не включились ({e}). Слушаю всё подряд.")

        self.pauser = AutoPause(cfg, self.journal, NullModel(), self._on_pause, self._on_resume)
        # отпечаток голоса (слушает только тебя) и что ты сейчас делаешь
        self.voiceprint = None
        self.enrolling = 0
        if not text_mode:
            try:
                from voiceprint import VoicePrint
                self.voiceprint = VoicePrint(cfg["_data_dir"], cfg.get("voiceprint", {}).get("threshold", 0.32))
                print(f"[голос] отпечаток: {'есть — слушаю только тебя' if self.voiceprint.active else 'не записан'}")
            except Exception as e:
                print(f"[голос] узнавание голоса недоступно: {e}")
        from activity import Activity
        self.activity = Activity()
        from initiative import Initiative
        self.initiative = Initiative(self, cfg)
        self.load_character()

    # --- имена и характер ---
    @property
    def user(self) -> str:
        return self.cfg["user_name"]

    def load_character(self):
        self.character = (ROOT / self.cfg["character_file"]).read_text(encoding="utf-8").format(
            name=self.cfg["companion_name"], user=self.user)
        self.journal.user = self.user
        self.ui.title(self.cfg["companion_name"])

    def update_settings(self, values: dict):
        save_user_settings(self.cfg, values)
        self.load_character()
        voice = getattr(self.speaker, "voice", None)
        if voice is not None and hasattr(voice, "apply"):
            voice.apply()              # новый голос/тон сразу, без перезапуска

    # --- ключ и запуск мозга ---
    def has_key(self) -> bool:
        return has_key()

    def try_key(self, key: str) -> dict:
        key = "".join(key.split()).strip('"')
        if not (key.startswith("AQ.") or key.startswith("AIza")) or not 30 <= len(key) <= 400:
            return {"ok": False, "msg": "Это не ключ: он начинается на AQ. или AIza"}
        try:
            from google import genai
            client = genai.Client(api_key=key)
            next(iter(client.models.list()))      # быстрая проверка, что Google принимает ключ
        except Exception as e:
            msg = str(e)
            if "API key" in msg or "401" in msg or "403" in msg or "400" in msg:
                return {"ok": False, "msg": "Google не принял ключ. Скопируй его ещё раз целиком."}
            return {"ok": False, "msg": "Нет связи с Google. Проверь интернет и попробуй снова."}
        save_key(key)
        self.ui.key_ok()
        threading.Thread(target=self.start_brain, daemon=True).start()
        return {"ok": True}

    def start_brain(self):
        if self.ready.is_set():
            return
        b = self.cfg["brain"]
        self.brain = GeminiBrain(b["model"], thinking_budget=b.get("thinking_budget"))
        def _migrate():
            try:
                self.memory.migrate(self.brain)
            except Exception as e:
                print(f"[память] разложить старое не получилось: {e}")
        threading.Thread(target=_migrate, daemon=True).start()
        if not self.text_mode:
            from tts import Speaker, make_voice
            self.speaker = Speaker(make_voice(self.cfg, ROOT, HOME), on_talk=self._on_talk,
                                   on_text=self.ui.her, on_amp=self.ui.mouth)
            if hasattr(self.speaker.voice, "notify"):
                self.speaker.voice.notify = lambda m: (print(m), self.ui.add("sys", m))
        self.ready.set()

    # --- состояние на экране ---
    def _idle_state(self) -> str:
        if self.pauser.paused:
            return "pause"
        return "listen" if self.awake else "sleep"

    def _on_talk(self, talking: bool) -> None:
        self.ui.state("talk" if talking else self._idle_state())

    def _on_level(self, v: float) -> None:
        t = time.monotonic()
        if t - self._level_t > 0.12:              # ~8 раз в секунду, чтобы не грузить окно
            self._level_t = t
            self.ui.level(v)

    # --- системная подсказка ---
    def system(self, wake: str | None = None) -> str:
        from wake_context import WEEKDAYS
        t = now()
        reminders = "; ".join(f"{r['at'][11:16]} — {r['text']}" for r in self.initiative.pending())
        parts = [self.character, "",
                 f"## Сейчас\n{WEEKDAYS[t.weekday()]}, {t.strftime('%d.%m.%Y %H:%M')}"
                 + (f"\nУже стоят напоминания: {reminders}" if reminders else ""), "",
                 "## Память о " + self.user,
                 self.memory.read() or "(пока пусто)", "", "## Последние события",
                 self.journal.render(8) or "(пусто)"]
        parts += ["", "## Твой характер сейчас (настройки " + self.user + ")", traits_text(self.cfg.get("traits", {}))]
        doing = self.activity.describe() if hasattr(self, "activity") else None
        if doing:
            parts += ["", "## Чем он занят", doing + " Можешь иногда к месту это упомянуть, но не каждый раз."]
        if getattr(self, "lang", "ru") == "en":
            parts += ["", "## Режим: практика английского",
                      f"Говори с {self.user} по-английски, простыми фразами. Если он ошибся — мягко "
                      f"повтори правильный вариант одной фразой и продолжай разговор. Эмоции в {{}} и "
                      f"команды оставляй по-русски, как обычно."]
        if wake:
            parts += ["", "## Ты только что вернулась", wake]
        parts.append(FORMAT_RULES.format(user=self.user))
        return "\n".join(parts)

    # --- речь ---
    def _mute(self):
        self.speaking = True
        if self.listener and not self.barge:      # в наушниках слушаем всегда — для перебивания
            self.listener.mute()

    def _unmute(self):
        self.speaking = False
        if self.listener and not self.pauser.paused and not self.barge:
            self.listener.unmute()

    # --- перебивание ---
    def _on_user_speech(self):
        """Ты заговорил. Если она в этот момент говорит или думает — замолкает и слушает."""
        if self.barge and self.speaking and self.awake and not self.pauser.paused:
            self.interrupt()

    def interrupt(self):
        print("✋ перебили — слушаю")
        self._cancel = True
        if self.speaker and hasattr(self.speaker, "stop"):
            self.speaker.stop()
        self.ui.her_done()
        self.ui.state("listen")

    def say(self, text: str, emotion: str = "calm") -> None:
        with self.busy:
            self._mute()
            self.ui.emotion(emotion)
            self.speaker.speak(text, emotion)
            self.speaker.wait_done()
            self._unmute()
        self.ui.her_done()
        self.ui.state(self._idle_state())
        self.ui.emotion(emotion, 4000)

    def say_generated(self, system: str, instruction: str, fallback: str = "Я тут!") -> None:
        """Одна фраза, которую она придумывает сама (приветствие, вопрос, напоминание)."""
        self._work_t = time.monotonic()
        self.ui.state("think")
        try:
            raw = self.brain.say_once(system, instruction + " Начни с эмоции в фигурных скобках, "
                                      "например {радость}. Без скобок [[ ]].")
        except Exception as e:
            print(f"[мозг] {e}")
            raw = fallback
        p = ReplyParser()
        p.feed(raw or fallback)
        text = " ".join(p.finish()) or p.reply or fallback
        self.say(text, p.emotion)
        self.history.append({"role": "model", "text": text})
        self._work_t = None

    def greet(self, reason: str, away_sec: float, since) -> None:
        wake = build_wake_context(self.journal, reason, away_sec, since, limit=5)
        self.say_generated(self.system(wake),
                           f"Скажи {self.user} одну-две живые фразы: поздоровайся или "
                           f"отреагируй на возвращение, учитывая подсказку.")

    def respond(self, wav: bytes | None = None, text: str | None = None,
                image: bytes | None = None) -> None:
        self._work_t = time.monotonic()
        self._cancel = False
        with self.busy:
            self._mute()
            self.ui.state("think")
            parser = ReplyParser()
            try:
                shown = False
                for chunk in self.brain.stream_reply(self.system(), list(self.history),
                                                     wav=wav, text=text, image=image):
                    if self._cancel:
                        break                          # её перебили — дальше не говорим
                    for sentence in parser.feed(chunk):
                        if not shown:
                            self.ui.emotion(parser.emotion)
                            shown = True
                        self.speaker.speak(sentence, parser.emotion)
                for sentence in ([] if self._cancel else parser.finish()):
                    if not shown:
                        self.ui.emotion(parser.emotion)
                        shown = True
                    self.speaker.speak(sentence, parser.emotion)
            except Exception as e:
                print(f"[мозг] ошибка: {e}")
                self.speaker.speak(self._error_line(e), "sad")
            self.speaker.wait_done()
            self._unmute()
        self.ui.her_done()
        self.ui.state(self._idle_state())
        self.ui.emotion(parser.emotion, 4000)
        self._work_t = None

        self.last_parser = parser
        if parser.commands:
            self.handle_commands(parser.commands)
        if parser.skip:
            print(f"   (не мне: «{parser.transcript}»)")
            return
        heard = parser.transcript or text or ""
        if heard:
            print(f"👂 {heard}")
            if wav:                                   # текст из окна уже показан
                self.ui.add("me", heard, "📷" if image else None)
            self.history.append({"role": "user", "text": heard + (" [скриншот экрана]" if image else "")})
            self.unsaved.append(f"{self.user}: {heard}")
        if parser.reply:
            self.history.append({"role": "model", "text": parser.reply})
            self.unsaved.append(f"Она: {parser.reply}")
        self.last_talk = time.monotonic()

    @staticmethod
    def _error_line(e: Exception) -> str:
        msg = str(e)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
            return ("Кажется, бесплатный лимит Google на сегодня закончился. "
                    "Он обнулится в пять вечера по корейскому времени.")
        return "Ой, что-то со связью. Повтори, пожалуйста."

    # --- команды из ответа ---
    def handle_commands(self, commands: list[str]) -> None:
        import re as _re
        for c in commands:
            kind, _, arg = c.strip().partition(" ")
            kind = kind.upper()
            print(f"[команда] {kind} {arg}")
            if kind == "НАПОМНИТЬ":
                self.initiative.add_from_command(c)
            elif kind == "ТАЙМЕР":
                m = _re.match(r"\s*(\d{1,4})\s*(?:\|\s*(.*))?", arg)
                if m:
                    label = (m.group(2) or "").strip() or "время вышло"
                    self.initiative.add_from_command(f"НАПОМНИТЬ +{m.group(1)} | Таймер: {label}")
            elif kind in ("ОТКРЫТЬ", "МУЗЫКА", "ГРОМКОСТЬ"):
                threading.Thread(target=self._do_action, args=(kind, arg), daemon=True).start()
            elif kind == "ПОИСК":
                threading.Thread(target=self._do_search, args=(arg,), daemon=True).start()
            elif kind == "ПОКАЗАТЬ":
                self.ui.add("her", arg.strip(), "📝")
                self.ui.show_chat()
            elif kind == "РЕЖИМ":
                self.set_lang("en" if "eng" in arg.lower() or "англ" in arg.lower() else "ru")
            else:
                print(f"[команда] не знаю такую: {c}")

    def _do_action(self, kind: str, arg: str) -> None:
        import actions
        try:
            done = actions.run(kind, arg)
            print(f"[действие] {done}")
            self.journal.log("action", what=f"{kind} {arg}")
        except Exception as e:
            print(f"[действие] не получилось: {e}")
            self.ui.add("sys", f"Не получилось: {kind.lower()} {arg} ({str(e)[:80]})")

    def _do_search(self, query: str) -> None:
        city = self.cfg.get("user_city", "Пусан")
        t = now()
        try:
            facts = self.brain.search(query, f"Пользователь живёт в городе {city}. "
                                             f"Сейчас {t.strftime('%d.%m.%Y %H:%M')}.")
            print(f"[поиск] {query} → {facts[:200]}")
        except Exception as e:
            print(f"[поиск] не получилось: {e}")
            self.say("Не получилось найти, интернет капризничает.", "sad")
            return
        self.say_generated(self.system(),
                           f"Ты посмотрела в интернете по вопросу «{query}». Вот что нашлось: {facts}\n"
                           f"Перескажи {self.user} главное своими словами, коротко (1–3 предложения), "
                           f"без ссылок и списков.")
        self.last_talk = time.monotonic()

    # --- отпечаток голоса из настроек ---
    def start_enroll(self):
        if not self.voiceprint:
            self.ui.add("sys", "Узнавание голоса недоступно на этом Mac.")
            return
        self.awake = True
        self.ui.state("listen")
        self.voiceprint.forget()
        self.enrolling = 3
        self.say("Хорошо! Скажи мне пять любых фраз, по 2–3 секунды каждая, когда я замолчу — я запомню твой голос.", "joy")

    def forget_voice(self):
        if self.voiceprint:
            self.voiceprint.forget()
            self.enrolling = 0
            self.ui.add("sys", "Голос забыт: снова слушаю всех")

    # --- практика английского ---
    def set_lang(self, lang: str) -> None:
        if lang == getattr(self, "lang", "ru"):
            return
        self.lang = lang
        print(f"[язык] {lang}")
        voice = getattr(self.speaker, "voice", None)
        if voice is not None and hasattr(voice, "set_lang"):
            voice.set_lang(lang)
        self.ui.add("sys", "🇬🇧 Практика английского" if lang == "en" else "🇷🇺 Снова по-русски")

    # --- зрение ---
    def screenshot(self) -> bytes | None:
        from vision import capture
        self.ui.state("look")
        img = capture()
        if img is None:
            self.ui.add("sys", "Не вижу экран: разреши «Подруге» запись экрана — Системные настройки → "
                               "Конфиденциальность и безопасность → Запись экрана, потом перезапусти её.")
            if sys.platform == "darwin" and not getattr(self, "_asked_screen", False):
                self._asked_screen = True
                import subprocess
                subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"])
        return img

    def on_look_button(self):
        if not self.ready.is_set():
            return
        self.awake = True
        img = self.screenshot()
        self.ui.add("me", "Посмотри на экран", "📷")
        self.respond(text=LOOK_TEXT, image=img)

    def on_text(self, text: str):
        if not self.ready.is_set():
            return
        self.ui.add("me", text)
        if not self.awake:
            self.awake = True
        from wake import LOOK_PHRASES, _norm
        look = any(p in _norm(text) for p in LOOK_PHRASES)
        if not look and self.quick_answer(text=text):
            return
        self.respond(text=text, image=self.screenshot() if look else None)
        if is_goodbye(text, self.cfg["wake"]["sleep_phrases"]):
            self.go_sleep(say_goodnight=False)

    # --- сон и пробуждение ---
    def wake_up(self, has_request: bool, wav: bytes | None, look: bool = False) -> None:
        print("👋 проснулась")
        self.awake = True
        self.ui.state("listen")
        self.ui.act("wave", 2200)
        self.journal.log("wake")
        if has_request and wav:
            self.respond(wav=wav, image=self.screenshot() if look else None)
            return
        since = self.last_awake_at
        away = (now() - since).total_seconds() if since else 0
        if away < 2 * 3600 and self.quick_say("привет"):     # недавно виделись — сразу, без Google
            return
        self.greet("wake", away, since)

    def go_sleep(self, say_goodnight: bool = True) -> None:
        if say_goodnight:
            self.say(random.choice(self.cfg["wake"]["goodnight"]), "tender")
        self.awake = False
        self.last_awake_at = now()
        self.ui.state("sleep")
        self.journal.log("sleep")
        threading.Thread(target=self.save_memory, daemon=True).start()
        print(f"💤 уснула. Разбудить: «{self.cfg['wake']['phrases'][0]}»")

    # --- быстрые готовые ответы (replies.txt) ---
    def _after_question(self) -> bool:
        last = next((h["text"] for h in reversed(self.history) if h["role"] == "model"), "")
        return last.rstrip().endswith("?") and time.monotonic() - self.last_talk < 60

    def quick_reply(self, text: str):
        """→ (текст ответа, эмоция, команды) или None."""
        if not getattr(self, "quick", None) or getattr(self.speaker.voice, "lang", "ru") == "en":
            return None
        if is_goodbye(text, self.cfg["wake"]["sleep_phrases"]):
            return None
        m = self.quick.match(text, self._after_question())
        if not m:
            return None
        parts, emo, cmds = m
        reply = " ".join(self.quick.fill(t, ctx, self.user, self.cfg["companion_name"]) for t, ctx in parts)
        return reply, emo, cmds

    def quick_say(self, text: str) -> bool:
        r = self.quick_reply(text)
        if not r:
            return False
        reply, emo, _ = r
        self.say(reply, emo)
        self.history.append({"role": "model", "text": reply})
        self.last_talk = time.monotonic()
        return True

    def quick_answer(self, wav: bytes | None = None, text: str | None = None) -> bool:
        """Простая фраза — отвечаем сами за доли секунды. Сложное — False, пусть думает Gemini."""
        if not getattr(self, "quick", None):
            return False
        t0 = time.monotonic()
        if wav is not None:
            if not self.wake:
                return False
            heard, conf = self.wake.transcribe(wav)
            if not heard or conf < 0.7:
                return False
        else:
            heard = text or ""
        r = self.quick_reply(heard)
        if not r:
            return False
        reply, emo, cmds = r
        print(f"⚡ быстро ({(time.monotonic() - t0) * 1000:.0f} мс): «{heard}» → {reply}")
        if wav is not None:
            self.ui.add("me", heard)
        self.history.append({"role": "user", "text": heard})
        self.unsaved.append(f"{self.user}: {heard}")
        if cmds:
            self.handle_commands(cmds)
        self.say(reply, emo)
        self.history.append({"role": "model", "text": reply})
        self.unsaved.append(f"Она: {reply}")
        self.last_talk = time.monotonic()
        return True

    TOUCH_LINES = {
        "head": ["Хи-хи, приятно…", "Ещё погладь, пожалуйста.", "М-м, как хорошо.", "Ты такой заботливый."],
        "face": ["Эй, не тыкай!", "Ну щекотно же!", "Хм! Я дуюсь. Чуть-чуть.", "Ай! Что такое?"],
        "body": ["Ой… ты что делаешь?", "Эй, я смущаюсь!", "Ну-у, перестань."],
        "dropped": ["Ой, куда ты меня несёшь?", "Голова кружится…", "Вот тут мне нравится."],
    }

    def on_touch(self, zone: str) -> None:
        """Касание мышкой. Лицо и тело она показывает сама, а иногда ещё и что-то говорит."""
        if not self.ready.is_set() or self.text_mode:
            return
        now = time.monotonic()
        if not self.awake or self.busy.locked() or self.pauser.paused:
            return
        if now - getattr(self, "_touch_said", 0) < 25 or random.random() > 0.6:
            return
        self._touch_said = now
        emo = {"head": "joy", "face": "surprise", "body": "shy", "dropped": "surprise"}[zone]
        self.journal.log("touch", what=zone)
        self.say(random.choice(self.TOUCH_LINES[zone]), emo)

    # --- Telegram ---
    def start_telegram(self, token: str):
        from telegram_bot import TelegramBot
        if getattr(self, "tg", None):
            self.tg.stop()
        self.tg = TelegramBot(self, token, self.cfg["_data_dir"])
        self.tg.start()
        return self.tg

    def setup_telegram(self, token: str) -> dict:
        """Токен из настроек: проверяем, сохраняем, запускаем."""
        from config import set_env
        token = "".join((token or "").split())
        if not token:
            if getattr(self, "tg", None):
                self.tg.stop()
            self.tg = None
            set_env("TELEGRAM_TOKEN", None)
            return {"ok": True, "off": True}
        from telegram_bot import TelegramBot
        try:
            name = TelegramBot(self, token, self.cfg["_data_dir"]).check()
        except Exception as e:
            return {"ok": False, "msg": f"Токен не подошёл: {e}"}
        set_env("TELEGRAM_TOKEN", token)
        tg = self.start_telegram(token)
        return {"ok": True, "name": name, "paired": bool(tg.owner), "code": tg.code}

    def telegram_status(self) -> dict:
        tg = getattr(self, "tg", None)
        if not tg:
            return {"on": False}
        return {"on": True, "name": tg.name, "paired": bool(tg.owner), "code": tg.code}

    def reply_text(self, text: str, image: bytes | None = None, extra: str = "") -> str:
        """Ответ текстом, без голоса (для Telegram). Память и история — общие."""
        print(f"📱 {text}")
        self.ui.add("me", text, "📱")
        r = None if image else self.quick_reply(text)
        if r:                                            # простое — отвечаем сразу, без Google
            reply, _, cmds = r
            cmds = [c for c in cmds if c.split(" ")[0].upper() in ("ТАЙМЕР", "НАПОМНИТЬ")]
            if cmds:
                self.handle_commands(cmds)
            for h in ({"role": "user", "text": f"(в Telegram) {text}"}, {"role": "model", "text": reply}):
                self.history.append(h)
            self.unsaved += [f"{self.user} (в Telegram): {text}", f"Она: {reply}"]
            self.ui.add("her", reply, "📱")
            print(f"⚡ быстро (telegram): «{text}» → {reply}")
            return reply
        parser = ReplyParser()
        try:
            for chunk in self.brain.stream_reply(self.system() + extra, list(self.history),
                                                 text=text, image=image):
                parser.feed(chunk)
            parser.finish()
        except Exception as e:
            print(f"[мозг] ошибка (telegram): {e}")
            return self._error_line(e)
        reply = parser.reply.strip() or "🙂"
        allowed = [c for c in parser.commands if c.split(" ")[0].upper() in ("НАПОМНИТЬ", "ТАЙМЕР")]
        if allowed:
            self.handle_commands(allowed)
        query = next((c.partition(" ")[2] for c in parser.commands if c.upper().startswith("ПОИСК")), None)
        if query:
            try:
                facts = self.brain.search(query, f"Пользователь живёт в городе {self.cfg.get('user_city', 'Пусан')}. "
                                                 f"Сейчас {now().strftime('%d.%m.%Y %H:%M')}.")
                raw = self.brain.say_once(self.system() + extra,
                                          f"Ты посмотрела в интернете «{query}». Нашлось: {facts}\n"
                                          f"Перескажи главное коротко, 1–3 предложения, без ссылок.")
                p2 = ReplyParser()
                p2.feed(raw)
                p2.finish()
                reply = (reply + "\n\n" if parser.reply.strip() else "") + (p2.reply or raw)
            except Exception as e:
                print(f"[поиск] telegram: {e}")
        self.history.append({"role": "user", "text": f"(в Telegram) {text}" + (" [фото]" if image else "")})
        self.history.append({"role": "model", "text": reply})
        self.unsaved.append(f"{self.user} (в Telegram): {text}")
        self.unsaved.append(f"Она: {reply}")
        self.ui.add("her", reply, "📱")
        return reply

    def toggle_sleep(self):
        if not self.ready.is_set():
            return
        if self.awake:
            self.go_sleep()
        else:
            self.wake_up(False, None)

    def on_phrase(self, wav: bytes) -> None:
        # запись отпечатка голоса
        if self.enrolling and self.voiceprint:
            if self.speaking or len(wav) < 16000 * 2 * 1.2:   # её собственный голос или слишком коротко
                return
            left = self.voiceprint.enroll_add(wav)
            self.enrolling = left
            if left:
                self.say(f"Ага. Ещё {'одну фразу' if left == 1 else str(left) + ' фразы'}.", "calm")
            else:
                self.say("Запомнила твой голос! Теперь слушаю только тебя.", "joy")
                self.ui.add("sys", "🎙 Голос запомнен: чужие голоса она будет пропускать")
            return
        # чужой голос (видео, друзья, Discord) — пропускаем
        if self.voiceprint and self.voiceprint.active:
            ok, sc = self.voiceprint.is_owner(wav)
            if not ok:
                print(f"   (не твой голос: {sc:.2f} — пропускаю)")
                return
            print(f"   (твой голос: {sc:.2f})")
            self.voiceprint.adapt(wav, sc)
        if not self.wake:
            self.respond(wav=wav)
            return
        h = self.wake.check(wav)                      # на компьютере, бесплатно
        if not self.awake:
            if h.kind == "wake":
                self.wake_up(h.has_request, wav, h.look)
            return                                    # спит: всё остальное игнорирует
        # Засыпает только если «спокойной ночи» есть в настоящей расшифровке: быстрый
        # распознаватель с короткой грамматикой любую длинную фразу «слышит» как прощание.
        self.ui.act("nod", 1400)          # кивает: услышала
        if not h.look and self.quick_answer(wav=wav):
            return
        self.respond(wav=wav, image=self.screenshot() if h.look else None)
        p = self.last_parser
        if p and not p.skip and is_goodbye(p.transcript, self.cfg["wake"]["sleep_phrases"]):
            self.go_sleep(say_goodnight=False)

    def preview_voice(self, voice_name: str, pitch: str = "medium"):
        if not self.ready.is_set() or self.text_mode:
            return
        phrase = "Привет! Так звучит мой голос. Как тебе?"
        try:
            from config import SILERO_SPEAKERS
            router = self.speaker.voice
            if voice_name == "chatterbox":
                cb = router.chatterbox
                if cb is None or not cb.ready.is_set():
                    self.ui.add("sys", "Пробный голос включится после «Сохранить» — сначала он "
                                "установится (~3 ГБ, 5–15 минут). Я напишу, когда будет готов.")
                    return
                audio, rate = cb.synth(phrase, "joy")
            elif voice_name in SILERO_SPEAKERS:
                if router.silero is None or not router.silero.ready.wait(timeout=60):
                    self.ui.add("sys", "Голос ещё загружается, попробуй через минуту.")
                    return
                s = router.silero
                old = (s.speaker, s.pitch)
                s.speaker, s.pitch = voice_name, pitch
                try:
                    audio, rate = s.synth(phrase)
                finally:
                    s.speaker, s.pitch = old
            else:
                from voice_gemini import GeminiVoiceOut
                v = GeminiVoiceOut(self.cfg["voice"]["gemini_model"], voice_name,
                                   self.cfg["voice"].get("style", ""))
                audio, rate = v._cloud(phrase)
            from tts import resample, smooth
            self.speaker.on_talk(True)
            self.speaker.audio_q.put(smooth(resample(audio, rate)))
            self.speaker.wait_done()
        except Exception as e:
            self.ui.add("sys", f"Не получилось проиграть голос: {str(e)[:80]}")

    # --- память ---
    def save_memory(self) -> None:
        if not self.unsaved or not self.brain:
            return
        transcript, self.unsaved = "\n".join(self.unsaved), []
        try:
            facts = extract_facts(self.brain, transcript, self.user, self.memory.read())
        except Exception as e:
            print(f"[память] не удалось записать: {e}")
            return
        self.memory.add_facts(facts)
        try:
            self.memory.consolidate(self.brain, self.user)
        except Exception as e:
            print(f"[память] сжать не получилось: {e}")
        self.journal.log("conversation", summary="; ".join(facts) if facts else "болтали")
        if facts:
            print("💾 запомнила: " + "; ".join(facts))

    def _memory_loop(self):
        m = self.cfg["memory"]
        while True:
            time.sleep(5)
            idle = time.monotonic() - self.last_talk
            if self.unsaved and (idle >= m["save_after_idle_s"]
                                 or len(self.unsaved) >= m["save_after_turns"] * 2):
                self.save_memory()
            self.last_seen.touch()

    # --- пауза ---
    def _on_pause(self, reason, detail):
        self.save_memory()
        if self.awake and self.ready.is_set():
            self.say(PAUSE_LINES.get(reason, "Пауза."))
        self._mute()
        self.ui.state("pause")

    def _on_resume(self, reason, detail, away, since):
        self._unmute()
        self.ui.state(self._idle_state())
        if self.awake and self.ready.is_set():
            threading.Thread(target=self.greet, args=(reason, away, since), daemon=True).start()

    # --- запуск ---
    def run(self) -> None:
        if not self.text_mode:
            signal.signal(signal.SIGINT, lambda *a: self.ui.close() or sys.exit(0))
        try:
            self.ui.run(self._loop)
        finally:
            self.shutdown()

    def _loop(self) -> None:
        previous = self.last_seen.get()
        self.last_awake_at = previous
        self.journal.log("app_start")
        away = (now() - previous).total_seconds() if previous else 0

        try:
            from hotkeys import register
            print(f"Горячая клавиша паузы: {register(self.cfg['autopause'], self.pauser.toggle)}")
        except Exception as e:
            print(f"⚠ Горячая клавиша не включилась: {e}")
        threading.Thread(target=self.pauser.run, daemon=True).start()
        threading.Thread(target=self._memory_loop, daemon=True).start()
        threading.Thread(target=self._restart_watch, daemon=True).start()
        threading.Thread(target=self._blackbox, daemon=True).start()
        if not self.text_mode:
            threading.Thread(target=self.initiative.run, name="initiative", daemon=True).start()
            from life import Life
            Life(self).start()
            import menubar
            menubar.start(self)
            self.activity.start()
        upd = HOME / "updated_to.txt"
        if upd.exists():
            self.ui.add("sys", f"✨ Я обновилась до версии {upd.read_text().strip()}")
            upd.unlink()
        try:
            from quick import QuickReplies
            self.quick = QuickReplies(ROOT, self.cfg["_data_dir"])
        except Exception as e:
            self.quick = None
            print(f"[быстро] готовые ответы не загрузились: {e}")
        self.tg = None
        if os.environ.get("TELEGRAM_TOKEN"):
            self.start_telegram(os.environ["TELEGRAM_TOKEN"])

        # Ключ: если нет — окно само попросит и дождётся
        if not has_key():
            if self.text_mode:
                print("Нет ключа Gemini. Запусти setup_mac.command или открой приложение.")
                return
            self.ui.state("setup")
            self.ui.need_key()
            print("Жду ключ Gemini в окне…")
        else:
            self.start_brain()
        self.ready.wait()

        try:
            if self.text_mode:
                self.greet("start", away, previous)
                print("Пиши сообщения (выход — пустая строка).")
                while (line := input("> ").strip()):
                    self.respond(text=line)
                return

            from audio_in import Listener
            m = self.cfg["microphone"]
            self.listener = Listener(energy_threshold=m["energy_threshold"],
                                     end_silence_ms=m["end_silence_ms"],
                                     min_speech_ms=m["min_speech_ms"], device=m["device"],
                                     speech_prob=m.get("speech_prob", 0.6),
                                     min_density=m.get("min_density", 0.45),
                                     on_level=self._on_level, on_speech=self._on_user_speech)
            from audio_in import output_device_name, output_is_headphones
            mode = m.get("barge_in", "auto")
            self.barge = output_is_headphones() if mode == "auto" else bool(mode)
            print(f"[уши] вывод звука: «{output_device_name()}» → перебивание "
                  f"{'включено' if self.barge else 'выключено (колонки)'}")
            self.listener.start()
            if self.wake:
                self.ui.state("sleep")
                print(f"💤 Сплю. Разбудить: «{self.cfg['wake']['phrases'][0]}». "
                      f"Усыпить: «{self.cfg['wake']['sleep_phrases'][0]}».")
            else:
                self.ui.state("listen")
                self.greet("start", away, previous)
            for wav in self.listener.phrases():
                if not self.pauser.paused:
                    self.on_phrase(wav)
        except (KeyboardInterrupt, EOFError):
            pass
        except Exception as e:
            print(f"[ошибка] {e}")
            self.ui.add("sys", f"Ошибка: {str(e)[:120]}")
            raise
        finally:
            if self.text_mode:
                self.ui.close()

    # --- чёрный ящик ---
    def _blackbox(self):
        """Если ответ длится дольше 25 с — пишем в журнал, где застрял каждый поток."""
        import faulthandler
        dumped_for = None
        while True:
            time.sleep(2)
            t = self._work_t
            if t and time.monotonic() - t > 25 and dumped_for != t:
                dumped_for = t
                print("[чёрный ящик] ответ идёт дольше 25 с, где сейчас каждый поток:")
                sys.stdout.flush()
                faulthandler.dump_traceback(file=sys.__stderr__, all_threads=True)

    # --- обновления на лету ---
    def _restart_watch(self):
        """Обновление без переустановки: после замены файлов рядом кладётся restart.flag —
        она сама сохраняет память и перезапускается с новым кодом."""
        flag = HOME / "restart.flag"
        while True:
            time.sleep(2)
            if not flag.exists():
                continue
            try:
                flag.unlink()
            except OSError:
                pass
            print("[обновление] перезапускаюсь с новой версией")
            self.shutdown(exit_process=False)        # сначала сохранить память и всё закрыть
            bundle = os.environ.get("PODRUGA_APP")
            if bundle:
                import subprocess
                # -n: новый экземпляр, даже если старый ещё не до конца закрылся
                subprocess.Popen(["/bin/sh", "-c", f'sleep 1; open -n "{bundle}"'],
                                 start_new_session=True)
                os._exit(0)
            os.execv(sys.executable, [sys.executable] + sys.argv)

    def shutdown(self, exit_process: bool = True) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self.pauser.stop()
        self.save_memory()
        self.last_seen.touch()
        self.journal.log("app_stop")
        print("\nПока!")
        if not self.text_mode and exit_process:
            os._exit(0)     # фоновые потоки (микрофон) не держат программу после закрытия окна


def traits_text(t: dict) -> str:
    """Ползунки 0–100 → указания для мозга."""
    def pick(v, low, mid, high):
        return low if v < 34 else high if v > 66 else mid
    bold = int(t.get("trait_bold", 20)); play = int(t.get("trait_play", 55)); talk = int(t.get("trait_talk", 30))
    return "\n".join([
        "- " + pick(bold, "Очень мягкая и нежная: никаких подколов, только тепло и забота.",
                    "Мягкая, но с характером: можешь по-доброму пошутить.",
                    "Дерзкая и острая на язык: подкалываешь и споришь, но любя, без грубости."),
        "- " + pick(play, "Спокойная и серьёзная, без лишних шуток.",
                    "В меру игривая: шутишь к месту.",
                    "Очень игривая и весёлая: часто шутишь, дурачишься, радуешься мелочам."),
        "- " + pick(talk, "Говоришь очень коротко: одна фраза, иногда пара слов.",
                    "Отвечаешь 1–2 предложениями.",
                    "Любишь поболтать: 2–4 предложения, рассказываешь и расспрашиваешь."),
    ])


class _PrintSpeaker:
    def speak(self, text, emotion="calm"): print(f"🗣  {text}")
    def wait_done(self): pass


_NO_NAP = None


def keep_awake_for_user() -> None:
    """macOS «App Nap» тормозит фоновые приложения с почти прозрачным окном: ответы шли по 15–20 с,
    анимация дёргалась. Говорим системе, что мы — работа для пользователя и нам важна скорость."""
    global _NO_NAP
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSProcessInfo
        user_initiated_allow_sleep = 0x00EFFFFF        # NSActivityUserInitiatedAllowingIdleSystemSleep
        latency_critical = 0xFF00000000                # NSActivityLatencyCritical
        _NO_NAP = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
            user_initiated_allow_sleep | latency_critical, "Подруга слушает и отвечает голосом")
        print("[система] App Nap выключен для Подруги")
    except Exception as e:
        print(f"[система] не удалось выключить App Nap: {e}")


if __name__ == "__main__":
    logsetup.setup()
    keep_awake_for_user()
    Companion(load_config(), text_mode="--text" in sys.argv).run()
