#!/bin/bash
# Обновление: ставит новые пакеты и скачивает то, чего не хватает. Ключ не трогает.
cd "$(dirname "$0")"
source .venv/bin/activate
echo "Ставлю новые пакеты..."
pip install -q -r requirements.txt || { read -p "Ошибка установки. Пришли текст выше Claude. Enter"; exit 1; }
if [ ! -d voices/vosk-model-small-ru-0.22 ]; then
  echo "Скачиваю распознаватель фразы «привет, подруга» (~45 МБ)..."
  curl -L --fail -o voices/vosk-ru.zip https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip \
    && (cd voices && unzip -q vosk-ru.zip && rm vosk-ru.zip) \
    && echo "Готово." || echo "⚠ Не скачалось — пришли текст выше Claude."
fi
echo ""
echo "Обновление закончено. Запускай start_mac.command."
read -p "Нажми Enter, чтобы закрыть"
