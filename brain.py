"""Облачный мозг: Gemini. Принимает аудио фразы, сам понимает речь и отвечает текстом."""
import os
import threading
import time

FORMAT_RULES = """
Как отвечать:
- Начни ответ с дословной расшифровки того, что сказал {user}, в двойных квадратных скобках: [[...]]
  (если он написал текстом или его речь уже расшифрована — скобки [[...]] НЕ пиши, сразу эмоция)
- Сразу после неё — твоя эмоция в фигурных скобках, ровно одна из:
  {{радость}} {{нежность}} {{смущение}} {{удивление}} {{грусть}} {{задумчивость}} {{спокойно}}
  Выбирай честно по смыслу: комплимент тебе — смущение, его успех — радость,
  ему плохо — грусть или нежность, вопрос на подумать — задумчивость.
- Команды (ставь после эмоции, вслух не произноси; можно несколько):
  <<НАПОМНИТЬ ЧЧ:ММ | что>> или <<НАПОМНИТЬ +N | что>> — напоминание (время — по разделу «Сейчас»);
  <<ТАЙМЕР N | на что>> — таймер на N минут;
  <<ОТКРЫТЬ что>> — открыть сайт или программу (YouTube, Naver, Coupang, Telegram, Safari… или ссылку);
     «включи на ютубе котиков» → <<ОТКРЫТЬ youtube котики>>;
  <<МУЗЫКА play|pause|next|prev>> — управлять музыкой;
  <<ГРОМКОСТЬ +10|-10|50|mute>> — громкость Mac;
  <<ПОИСК запрос>> — если нужны свежие данные (погода, курс, новости, расписание, цены, «что нового»):
     сам не выдумывай цифры — поставь ПОИСК и скажи коротко «сейчас гляну»;
  <<ПОКАЗАТЬ текст>> — показать текст в окне (перевод, адрес, список). Перевод на корейский/английский
     покажи так, а вслух скажи по-русски коротко, что перевела;
  <<ГУЛЯТЬ погулять|влево|вправо|сесть|стоп>> — пройтись по экрану, присесть или остановиться;
  <<РЕЖИМ english>> — он хочет практиковать английский (дальше говори по-английски, просто, и мягко
     поправляй его ошибки); <<РЕЖИМ русский>> — вернуться к русскому.
- Затем твой ответ. Коротко, как в живом разговоре: 1–3 предложения.
- Без списков, смайликов, звёздочек и markdown — твой ответ будет озвучен голосом.
- «Привет, подруга» / «эй, подруга» — это просто как тебя зовут, не отвечай на это отдельно,
  отвечай на то, что сказано после. «Спокойной ночи» / «пока, подруга» — коротко попрощайся, ты засыпаешь.
- Если фраза явно не к тебе — ответь только: [[...]] <МОЛЧУ>. Не к тебе, например:
  он обращается к другому человеку по имени («Марина, я ещё сделаю…», «Сань, подай…»),
  говорит по телефону, договаривается с кем-то рядом («я сам сделаю», «давай потом»),
  это звук видео или игры, или в аудио нет слов. Если сомневаешься и тебя не звали — лучше промолчи.
  К тебе: когда зовёт по имени или «подруга», спрашивает тебя, или продолжает ваш разговор.
- Если к сообщению приложен скриншот — это экран {user} прямо сейчас. Опирайся на то, что
  на нём видно; если просит помочь — объясни по шагам, куда нажать. Не зачитывай всё подряд.
Пример: [[привет, как дела?]] {{радость}} Привет! У меня всё хорошо, а у тебя как день прошёл?
"""


TIMEOUT_MS = 30_000


class NullModel:
    """Заглушка для автопаузы, когда мозг в облаке: выгружать из видеокарты нечего."""
    def unload(self): return True
    def preload(self, *a, **k): return True


class GeminiBrain:
    def __init__(self, model: str, api_key: str | None = None, thinking_budget: int | None = 0):
        from google import genai  # импорт здесь, чтобы остальные модули работали без пакета
        from google.genai import types
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Нет ключа. Возьми бесплатный в Google AI Studio и выполни: "
                               "setx GEMINI_API_KEY \"твой_ключ\" (потом перезапусти консоль)")
        self.types = types
        # timeout в мс: без него при плохой связи она могла «думать» бесконечно
        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        self.model = model
        # Разные модели Gemini понимают «раздумья» по-разному. Пробуем по очереди
        # и запоминаем первый вариант, который модель приняла.
        # Первым идёт режим текущей модели: неподходящий тратит лишний запрос и секунды на первый ответ.
        self.modes = ["level_minimal", "budget0", "none"] if thinking_budget == 0 else ["none"]

    def _config(self, system: str | None, temperature: float, max_tokens: int, mode: str):
        t = self.types
        kwargs = dict(temperature=temperature, max_output_tokens=max_tokens)
        if system:
            kwargs["system_instruction"] = system
        if mode == "budget0":
            kwargs["thinking_config"] = t.ThinkingConfig(thinking_budget=0)
        elif mode == "level_minimal":
            kwargs["thinking_config"] = t.ThinkingConfig(thinking_level="minimal")
        return t.GenerateContentConfig(**kwargs)

    def _call(self, contents, system, temperature, max_tokens, stream):
        fn = (self.client.models.generate_content_stream if stream
              else self.client.models.generate_content)
        while True:
            mode = self.modes[0]
            try:
                t0 = time.monotonic()
                result = fn(model=self.model, contents=contents,
                            config=self._config(system, temperature, max_tokens, mode))
                if stream:
                    result = self._first_checked(result)  # ошибка стрима всплывает на 1-м куске
                print(f"[мозг] ответ пошёл через {time.monotonic() - t0:.1f} с (режим {mode})")
                return result
            except Exception as e:
                if "400" in str(e) and len(self.modes) > 1:
                    print(f"[мозг] модель не приняла режим {mode}, пробую следующий")
                    self.modes.pop(0)
                    continue
                raise

    HEDGE_S = 4.5

    def _call_hedged(self, contents, system, temperature, max_tokens):
        """Бесплатный Gemini иногда держит запрос в очереди 10–20 с. Если ответ не начался за
        HEDGE_S секунд, отправляем тот же запрос второй раз и берём тот, что ответит раньше."""
        import queue
        q: queue.Queue = queue.Queue()

        def worker(i):
            try:
                q.put((i, self._call(contents, system, temperature, max_tokens, stream=True), None))
            except Exception as e:
                q.put((i, None, e))

        threading.Thread(target=worker, args=(0,), daemon=True).start()
        running, last_err = 1, None
        try:
            item = q.get(timeout=self.HEDGE_S)
        except queue.Empty:
            print(f"[мозг] Google молчит {self.HEDGE_S} с — отправляю запрос ещё раз")
            threading.Thread(target=worker, args=(1,), daemon=True).start()
            running += 1
            item = None
        while True:
            if item is None:
                try:
                    item = q.get(timeout=TIMEOUT_MS / 1000 + 5)
                except queue.Empty:
                    raise TimeoutError("Google не ответил")
            i, res, err = item
            running -= 1
            if err is None:
                if i == 1:
                    print("[мозг] второй запрос оказался быстрее")
                return res
            last_err = err
            if running == 0:
                raise last_err
            item = None

    @staticmethod
    def _first_checked(stream):
        it = iter(stream)
        try:
            first = next(it)
        except StopIteration:
            return iter(())

        def gen():
            yield first
            yield from it
        return gen()

    def _history(self, history: list[dict]):
        """Gemini ждёт, что разговор начинается с пользователя и роли чередуются."""
        t = self.types
        merged: list[dict] = []
        for h in history:
            if merged and merged[-1]["role"] == h["role"]:
                merged[-1] = {"role": h["role"], "text": merged[-1]["text"] + "\n" + h["text"]}
            else:
                merged.append(dict(h))
        if merged and merged[0]["role"] == "model":
            merged.insert(0, {"role": "user", "text": "(начало разговора)"})
        if merged and merged[-1]["role"] == "user":
            merged.append({"role": "model", "text": "(не расслышала)"})
        return [t.Content(role=h["role"], parts=[t.Part.from_text(text=h["text"])])
                for h in merged]

    def stream_reply(self, system: str, history: list[dict],
                     wav: bytes | None = None, text: str | None = None,
                     image: bytes | None = None, image_mime: str = "image/jpeg"):
        """Отдаёт ответ кусками по мере генерации."""
        t = self.types
        parts = []
        if wav:
            parts.append(t.Part.from_bytes(data=wav, mime_type="audio/wav"))
        if image:
            parts.append(t.Part.from_bytes(data=image, mime_type=image_mime))
        if text:
            parts.append(t.Part.from_text(text=text))
        contents = self._history(history) + [t.Content(role="user", parts=parts)]
        for chunk in self._call_hedged(contents, system, 0.9, 400):
            if getattr(chunk, "text", None):
                yield chunk.text

    def say_once(self, system: str, instruction: str) -> str:
        """Одна фраза без аудио — например, приветствие при запуске."""
        r = self._call(instruction, system, 0.9, 200, stream=False)
        return (r.text or "").strip()

    def search(self, query: str, context: str = "") -> str:
        """Свежие данные из интернета через поиск Google (погода, курс, новости, факты)."""
        t = self.types
        last = None
        for mode in list(self.modes) + ["none"]:
            cfg = self._config("Ты ищешь свежую информацию и отвечаешь фактами, коротко, по-русски. "
                               + context, 0.3, 500, mode)
            cfg.tools = [t.Tool(google_search=t.GoogleSearch())]
            try:
                r = self.client.models.generate_content(model=self.model, contents=query, config=cfg)
                return (r.text or "").strip()
            except Exception as e:
                last = e
                if "400" not in str(e):
                    break
        raise last

    def chat(self, messages: list[dict], options: dict | None = None) -> str:
        """Совместимо с memory.extract_facts (тот же интерфейс, что у Ollama)."""
        text = "\n\n".join(m["content"] for m in messages)
        temp = (options or {}).get("temperature", 0.7)
        r = self._call(text, None, temp, 300, stream=False)
        return r.text or ""
