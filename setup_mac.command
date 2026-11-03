#!/bin/bash
# Установка на Mac. Запускать один раз двойным кликом.
cd "$(dirname "$0")"
echo "=== Установка ИИ-компаньона ==="

PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Нужен Python 3.11 или новее. Открываю python.org — скачай «macOS installer», установи и запусти этот файл снова."
  open "https://www.python.org/downloads/macos/"
  read -p "Нажми Enter, чтобы закрыть"; exit 1
fi
echo "Python: $($PY --version)"

"$PY" -m venv .venv || { read -p "Не удалось создать окружение. Enter"; exit 1; }
source .venv/bin/activate
pip install --upgrade pip -q
echo "Ставлю пакеты (пару минут)..."
pip install -r requirements.txt || { read -p "Ошибка установки пакетов. Пришли текст выше Claude. Enter"; exit 1; }

echo "Скачиваю русский голос..."
python -m piper.download_voices ru_RU-irina-medium --data-dir voices

if [ ! -d voices/vosk-model-small-ru-0.22 ]; then
  echo "Скачиваю распознаватель фразы «привет, подруга» (~45 МБ)..."
  curl -L --fail -o voices/vosk-ru.zip https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip \
    && (cd voices && unzip -q vosk-ru.zip && rm vosk-ru.zip) \
    || echo "⚠ Не скачалось. Она будет слушать всё подряд, без фразы-активатора."
fi

while [ ! -f .env ]; do
  echo ""
  echo "Вставь ключ Gemini (Cmd+V) и нажми Enter."
  echo "Ключ начинается на AQ. (новый формат) или AIza (старый)."
  read -r KEY
  KEY="$(echo "$KEY" | tr -d '[:space:]"')"
  if { [[ "$KEY" == AIza* ]] || [[ "$KEY" == AQ.* ]]; } && [ ${#KEY} -ge 30 ] && [ ${#KEY} -le 400 ] && [[ "$KEY" != *http* ]]; then
    echo "GEMINI_API_KEY=$KEY" > .env
    chmod 600 .env
    clear
    echo "Ключ сохранён."
  else
    echo "⚠ Это не ключ (начинается на «${KEY:0:6}», длина ${#KEY})."
    echo "  В AI Studio нажми на ключ «…feHw» → в строке «API Key» значок копирования справа."
  fi
done

echo ""
echo "Модели, доступные по ключу (нужна flash-lite):"
python list_models.py || echo "⚠ Ключ не подошёл. Удали файл .env и запусти установку снова."

chmod +x start_mac.command start_text_mac.command mic_test_mac.command 2>/dev/null
echo ""
echo "Готово! Дальше: start_text_mac.command (проверка текстом), потом start_mac.command."
read -p "Нажми Enter, чтобы закрыть"
