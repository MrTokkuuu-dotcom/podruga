"""Разбирает ответ мозга на лету.
Мозг отвечает так:  [[что сказал пользователь]] {эмоция} <<КОМАНДА>> ответ...
- расшифровку забираем в историю;
- {эмоция} — для лица и голоса;
- <<...>> — служебные команды (например, напоминание), вслух не произносятся;
- ответ режем на предложения и сразу отдаём голосу, не дожидаясь конца."""
import re

SILENT = "<МОЛЧУ>"
_SENTENCE_END = re.compile(r"(.+?[.!?…]+)(\s+|$)", re.S)
_STRAY = re.compile(r"\{[^{}]{0,30}\}|<<[^<>]*>>|\[\[|\]\]")

EMOTIONS = {
    "радость": "joy", "весело": "joy", "счастье": "joy",
    "нежность": "tender", "забота": "tender", "тепло": "tender",
    "смущение": "shy", "стеснение": "shy",
    "удивление": "surprise", "восторг": "surprise",
    "грусть": "sad", "сочувствие": "sad", "печаль": "sad",
    "задумчивость": "think", "интерес": "think",
    "спокойно": "calm", "нейтрально": "calm",
}


def emotion_id(word: str) -> str:
    return EMOTIONS.get(word.strip().lower().replace("ё", "е"), "calm")


class ReplyParser:
    def __init__(self):
        self._head = ""          # пока не нашли ]]
        self._body = ""          # текст ответа, ещё не отданный голосу
        self.transcript = ""
        self.reply = ""
        self.skip = False
        self.emotion = "calm"
        self.commands: list[str] = []
        self._in_body = False
        self._tags_done = False

    def feed(self, chunk: str) -> list[str]:
        if self.skip:
            return []
        if not self._in_body:
            self._head += chunk
            start = self._head.lstrip()
            if start.startswith("[["):
                end = start.find("]]")
                if end == -1:
                    return []
                self.transcript = start[2:end].strip()
                rest = start[end + 2:]
            elif len(start) >= 2 or not start.startswith("["):
                rest = start  # модель забыла формат — считаем всё ответом
                if start.startswith("[") and len(start) < 2:
                    return []
            else:
                return []
            self._in_body = True
            self._head = ""
            chunk = rest
        self._body += chunk
        if SILENT in self._body:
            self.skip = True
            self._body = ""
            return []
        if not self._take_tags(final=False):
            return []
        return self._pop_sentences(final=False)

    def finish(self) -> list[str]:
        if self.skip:
            return []
        if not self._in_body and self._head.strip():
            self.feed("")  # короткий ответ без ]]
            if not self._in_body:
                self._body, self._head = self._head, ""
        if SILENT in self._body:
            self.skip = True
            return []
        self._take_tags(final=True)
        return self._pop_sentences(final=True)

    def _take_tags(self, final: bool) -> bool:
        """Снимает {эмоцию} и <<команды>> в начале ответа. False — ждём ещё текста."""
        while not self._tags_done:
            b = self._body.lstrip()
            if b.startswith("{"):
                j = b.find("}")
                if j == -1:
                    if final or len(b) > 40:
                        self._tags_done = True
                        break
                    return False
                self.emotion = emotion_id(b[1:j])
                self._body = b[j + 1:]
                continue
            if b.startswith("<<"):
                j = b.find(">>")
                if j == -1:
                    if final or len(b) > 300:
                        self._tags_done = True
                        break
                    return False
                self.commands.append(b[2:j].strip())
                self._body = b[j + 2:]
                continue
            if not final and (b == "" or b == "<"):
                return False
            self._tags_done = True
        return True

    def _pop_sentences(self, final: bool) -> list[str]:
        out = []
        while True:
            m = _SENTENCE_END.match(self._body)
            if not m or (not m.group(2) and not final):
                break  # последнее предложение может быть ещё не дописано
            out.append(m.group(1).strip())
            self._body = self._body[m.end():]
        if final and self._body.strip():
            out.append(self._body.strip())
            self._body = ""
        out = [" ".join(_STRAY.sub(" ", s).split()) for s in out]
        out = [s for s in out if s and any(ch.isalnum() for ch in s)]
        self.reply += (" " if self.reply and out else "") + " ".join(out)
        return out

