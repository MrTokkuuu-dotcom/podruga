#!/bin/bash
# Установщик «Подруги» для Mac. Запускается двойным кликом, ничего вводить не нужно.
# Всё ставится в папку ~/Podruga (код, свой Python, память) и создаётся приложение «Подруга».
set -u
SRC="$(cd "$(dirname "$0")" && pwd)"
H="$HOME/Podruga"
OLD="$HOME/Library/Application Support/Podruga"
APP="$H/app"
VENV="$H/venv"
BIN="$H/bin"
VOSK="vosk-model-small-ru-0.22"

say_step() { echo ""; echo "▶ $1"; }
fail() {
  echo ""; echo "❌ $1"
  echo "Сделай скриншот этого окна и пришли тому, кто дал тебе установщик."
  read -r -p "Нажми Enter, чтобы закрыть"; exit 1
}

clear
echo "macOS $(sw_vers -productVersion 2>/dev/null), процессор $(uname -m)"
MAJOR="$(sw_vers -productVersion 2>/dev/null | cut -d. -f1)"
if [ -n "$MAJOR" ] && [ "$MAJOR" -lt 11 ]; then
  fail "Нужна macOS 11 (Big Sur) или новее."
fi
[ "$(uname -m)" = "arm64" ] || echo "⚠ Mac на Intel: всё заработает, но голос будет попроще (Silero только для M-чипов)."
echo "=============================================="
echo "      Установка «Подруги» 💜  (~5 минут)"
echo "=============================================="
[ -d "$SRC/app" ] || fail "Не нашла папку app рядом с установщиком. Распакуй архив целиком."

# закрыть запущенную «Подругу», чтобы обновить файлы
pkill -f "Podruga/venv/bin/python" 2>/dev/null
pkill -f "Application Support/Podruga/venv/bin/python" 2>/dev/null

# переезд со старого места (первая версия ставилась в ~/Library)
if [ -d "$OLD" ] && [ ! -d "$H" ]; then
  say_step "Переношу прошлую установку в папку Podruga"
  mkdir -p "$H"
  for x in .env data bin; do [ -e "$OLD/$x" ] && mv "$OLD/$x" "$H/"; done
  [ -d "$OLD/app/voices" ] && mkdir -p "$APP" && mv "$OLD/app/voices" "$APP/voices"
  rm -rf "$OLD"
fi
mkdir -p "$H" "$BIN" || fail "Не получилось создать папку программы."

say_step "1/6 Копирую программу"
mkdir -p "$APP"
# код обновляем, а скачанные голоса и модели оставляем
rsync -a --delete --exclude "voices/" --exclude "__pycache__/" "$SRC/app/" "$APP/" || fail "Не получилось скопировать файлы."
mkdir -p "$APP/voices"

say_step "2/6 Готовлю Python (свой, отдельный — системный не трогаю)"
UV="$BIN/uv"
if [ ! -x "$UV" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$BIN" UV_NO_MODIFY_PATH=1 INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null 2>&1 \
    || fail "Не получилось скачать установщик Python. Проверь интернет."
fi
[ -x "$UV" ] || fail "Установщик Python не появился."
if [ ! -x "$VENV/bin/python" ]; then
  "$UV" venv --python 3.11 --python-preference only-managed "$VENV" >/dev/null 2>&1 \
    || fail "Не получилось подготовить Python."
fi

say_step "3/6 Ставлю библиотеки (2–4 минуты)"
LOGI="$H/install_log.txt"
if ! "$UV" pip install --python "$VENV/bin/python" -r "$APP/requirements.txt" > "$LOGI" 2>&1; then
  echo ""; tail -15 "$LOGI"
  fail "Не получилось поставить библиотеки. Подробности в файле Podruga/install_log.txt"
fi
shasum "$APP/requirements.txt" | cut -d' ' -f1 > "$H/.deps_stamp"

say_step "4/6 Скачиваю голос и распознаватель команд"
if [ ! -f "$APP/voices/ru_RU-irina-medium.onnx" ]; then
  "$VENV/bin/python" -m piper.download_voices ru_RU-irina-medium --data-dir "$APP/voices" >/dev/null 2>&1 \
    || echo "   ⚠ запасной голос не скачался — не страшно, основной голос — Silero"
fi
if [ ! -d "$APP/voices/$VOSK" ]; then
  curl -L --fail -s -o "$APP/voices/vosk-ru.zip" "https://alphacephei.com/vosk/models/$VOSK.zip" \
    && (cd "$APP/voices" && unzip -q -o vosk-ru.zip && rm -f vosk-ru.zip) \
    || echo "   ⚠ распознаватель «привет, подруга» не скачался — она будет слушать всё подряд"
fi

say_step "5/6 Ключ и память"
if [ ! -f "$H/.env" ]; then
  if [ -f "$SRC/key.txt" ]; then
    KEY="$(tr -d '[:space:]' < "$SRC/key.txt")"
    printf 'GEMINI_API_KEY=%s\n' "$KEY" > "$H/.env" && chmod 600 "$H/.env"
    echo "   ключ из установщика сохранён"
  elif [ -f "$HOME/Desktop/companion/.env" ]; then
    cp "$HOME/Desktop/companion/.env" "$H/.env" && chmod 600 "$H/.env"
    echo "   взяла ключ из папки companion на Рабочем столе"
  else
    echo "   ключа нет — приложение само попросит его при первом запуске"
  fi
else
  echo "   ключ уже есть"
fi
if [ ! -d "$H/data" ] && [ -d "$HOME/Desktop/companion/data" ]; then
  cp -R "$HOME/Desktop/companion/data" "$H/data" && echo "   перенесла память из папки companion"
fi

say_step "6/6 Создаю приложение «Подруга»"
for d in "/Applications" "$HOME/Applications"; do rm -rf "$d/Подруга.app" 2>/dev/null; done
DEST="/Applications"
[ -w "$DEST" ] || { DEST="$HOME/Applications"; mkdir -p "$DEST"; }
BUNDLE="$DEST/Подруга.app"
mkdir -p "$BUNDLE/Contents/MacOS" "$BUNDLE/Contents/Resources"
cp "$APP/avatar/icon.icns" "$BUNDLE/Contents/Resources/icon.icns"
cat > "$BUNDLE/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Подруга</string>
  <key>CFBundleDisplayName</key><string>Подруга</string>
  <key>CFBundleIdentifier</key><string>app.podruga.companion</string>
  <key>CFBundleVersion</key><string>1.1</string>
  <key>CFBundleShortVersionString</key><string>1.1</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>Podruga</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSAppNapIsDisabled</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>Чтобы слышать, когда ты со мной говоришь.</string>
</dict>
</plist>
PLIST
cat > "$BUNDLE/Contents/MacOS/Podruga" <<'LAUNCH'
#!/bin/bash
H="$HOME/Podruga"
export PODRUGA_HOME="$H"
export PODRUGA_APP="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONUNBUFFERED=1
LOG="$H/log.txt"
[ -f "$LOG" ] && [ "$(stat -f%z "$LOG")" -gt 5000000 ] && mv -f "$LOG" "$LOG.old"
echo "======== запуск $(date '+%Y-%m-%d %H:%M:%S') ========" >> "$LOG"
cd "$H/app" || exit 1
exec "$H/venv/bin/python" main.py >> "$LOG" 2>&1
LAUNCH
chmod +x "$BUNDLE/Contents/MacOS/Podruga"
touch "$BUNDLE"
cp "$SRC/app/installer/uninstall.command" "$H/Удалить Подругу.command" 2>/dev/null && chmod +x "$H/Удалить Подругу.command"

echo ""
echo "=============================================="
echo "  ✅ Готово! «Подруга» лежит в: $DEST"
echo "  Открываю её. Mac спросит доступ к микрофону — нажми «Разрешить»."
echo "  Чтобы она видела экран: при первой просьбе «посмотри» разреши"
echo "  «Запись экрана» в Системных настройках."
echo "=============================================="
open "$BUNDLE"
read -r -p "Нажми Enter, чтобы закрыть это окно"
