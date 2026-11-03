"""Telegram-бот: она в телефоне. Та же память и характер, ответы текстом.
Токен бота хранится в ~/Podruga/.env (TELEGRAM_TOKEN), хозяин — в data/telegram.json.
Пишет только хозяину: первый, кто пришлёт код из окна приложения, становится им."""
import json
import random
import threading
import time
from pathlib import Path

import requests

API = "https://api.telegram.org/bot{token}/{method}"
FILE = "https://api.telegram.org/file/bot{token}/{path}"

TG_RULES = (
    "\n\n## Сейчас вы переписываетесь в Telegram\n"
    "Он пишет тебе с телефона, тебя не слышно — ты отвечаешь текстом. Пиши как в мессенджере: "
    "коротко, тепло, 1–4 предложения, можно один эмодзи. Не говори, что открываешь что-то на его "
    "компьютере: отсюда ты можешь только ставить напоминания и таймеры (они сработают и здесь, "
    "и дома на компьютере) и искать в интернете.")


class TelegramBot:
    def __init__(self, companion, token: str, data_dir: Path):
        self.c = companion
        self.token = token.strip()
        self.path = Path(data_dir) / "telegram.json"
        self.state = self._load()
        self.offset = 0
        self.name = None
        self.running = False
        self.lock = threading.Lock()
        if not self.state.get("owner") and not self.state.get("code"):
            self.state["code"] = f"{random.randint(0, 999999):06d}"
            self._save()

    # --- хранение ---
    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}

    def _save(self):
        self.path.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")

    @property
    def owner(self):
        return self.state.get("owner")

    @property
    def code(self):
        return self.state.get("code")

    def unpair(self):
        self.state = {"code": f"{random.randint(0, 999999):06d}"}
        self._save()

    # --- API ---
    def call(self, method: str, http_timeout: float = 15, **params):
        r = requests.post(API.format(token=self.token, method=method), json=params, timeout=http_timeout)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description", f"HTTP {r.status_code}"))
        return data["result"]

    def check(self) -> str:
        """Проверить токен. Возвращает имя бота."""
        me = self.call("getMe")
        self.name = me.get("username")
        return self.name

    def send(self, chat_id, text: str):
        try:
            self.call("sendMessage", chat_id=chat_id, text=text[:4000])
        except Exception as e:
            print(f"[telegram] не отправилось: {e}")

    def send_owner(self, text: str):
        if self.owner:
            self.send(self.owner, text)

    def _download(self, file_id: str) -> bytes | None:
        try:
            f = self.call("getFile", file_id=file_id)
            r = requests.get(FILE.format(token=self.token, path=f["file_path"]), timeout=30)
            return r.content if r.ok else None
        except Exception as e:
            print(f"[telegram] файл не скачался: {e}")
            return None

    # --- приём сообщений ---
    def start(self):
        self.running = True
        threading.Thread(target=self._loop, name="telegram", daemon=True).start()

    def stop(self):
        self.running = False

    def _loop(self):
        fails = 0
        try:
            print(f"[telegram] бот @{self.check()} на связи"
                  + ("" if self.owner else f", код привязки: {self.code}"))
        except Exception as e:
            print(f"[telegram] токен не подошёл: {e}")
            self.c.ui.add("sys", f"Telegram: токен не подошёл ({e}).")
            self.running = False
            return
        while self.running:
            try:
                ups = self.call("getUpdates", http_timeout=45, offset=self.offset, timeout=30)
                fails = 0
                for u in ups:
                    self.offset = u["update_id"] + 1
                    if "message" in u:
                        threading.Thread(target=self._handle, args=(u["message"],), daemon=True).start()
            except Exception as e:
                fails += 1
                if fails in (1, 10):
                    print(f"[telegram] нет связи: {e}")
                time.sleep(min(60, 3 * fails))

    def _handle(self, m: dict):
        chat = m.get("chat", {}).get("id")
        text = (m.get("text") or m.get("caption") or "").strip()
        if not self.owner:
            if text.strip() == self.code:
                self.state = {"owner": chat}
                self._save()
                self.send(chat, f"Привет! Это я, {self.c.cfg['companion_name']} 💙 Теперь можешь писать "
                                f"мне отсюда — я всё помню, как дома.")
                self.c.ui.add("sys", "📱 Telegram подключён — она теперь и в телефоне.")
                print(f"[telegram] привязан хозяин {chat}")
            else:
                self.send(chat, "Пришли код из окна приложения (⚙︎ → Telegram), чтобы я тебя узнала.")
            return
        if chat != self.owner:
            self.send(chat, "Извини, я переписываюсь только со своим человеком.")
            return
        if text in ("/start", "/help"):
            self.send(chat, "Я тут! Просто пиши мне. Можно присылать фото — я посмотрю.")
            return
        image = None
        if m.get("photo"):
            image = self._download(m["photo"][-1]["file_id"])
        if m.get("voice") or m.get("audio"):
            self.send(chat, "Голосовые пока не умею слушать, напиши текстом, пожалуйста 🙏")
            return
        if not text and not image:
            return
        self._typing(chat)
        reply = self.c.reply_text(text or "Посмотри на фото.", image=image, extra=TG_RULES)
        self.send(chat, reply)

    def _typing(self, chat):
        try:
            self.call("sendChatAction", chat_id=chat, action="typing")
        except Exception:
            pass
