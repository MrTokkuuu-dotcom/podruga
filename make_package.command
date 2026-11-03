#!/bin/bash
# Собирает установщик для друга: Podruga-установщик.zip на Рабочем столе.
# Берёт ту версию, которая сейчас установлена и работает у тебя (~/Podruga/app).
H="$HOME/Podruga"
if [ -d "$H/app" ]; then SRC="$H/app"; else SRC="$(cd "$(dirname "$0")" && pwd)"; fi
OUT="$HOME/Desktop/Podruga-установщик"
rm -rf "$OUT" "$HOME/Desktop/Podruga-установщик.zip"
mkdir -p "$OUT/app"
rsync -a --exclude ".venv/" --exclude "venv/" --exclude "data/" --exclude "voices/" --exclude "__pycache__/" \
  --exclude ".env" --exclude ".env_*" --exclude ".DS_Store" --exclude "/*.command" --exclude "_old/" \
  --exclude "*.tmpnew" --exclude "avatar_window.py" --exclude "__MACOSX/" "$SRC/" "$OUT/app/"
cp "$SRC/installer/install.command" "$OUT/Установить Подругу.command"
cp "$SRC/make_package.command" "$OUT/app/make_package.command" 2>/dev/null
chmod +x "$OUT/Установить Подругу.command" "$OUT/app/installer/"*.command
cp "$SRC/installer/HOWTO.txt" "$OUT/Как установить.txt"

echo ""
echo "Встроить ТВОЙ ключ Gemini, чтобы у друга заработало сразу, без ввода ключа?"
echo "  y — да (у вас будет общий бесплатный лимит; ключ можно потом удалить в AI Studio)"
echo "  n — нет (приложение само попросит у друга его ключ)"
read -r A
if [ "$A" = "y" ]; then
  if [ -f "$H/.env" ]; then KEYFILE="$H/.env"; else KEYFILE="$SRC/.env"; fi
  if [ -f "$KEYFILE" ]; then
    grep GEMINI_API_KEY "$KEYFILE" | cut -d= -f2- > "$OUT/key.txt"
    echo "Ключ встроен."
  else
    echo "Ключ не нашла — собираю без него."
  fi
fi
(cd "$HOME/Desktop" && zip -qr "Podruga-установщик.zip" "Podruga-установщик") && rm -rf "$OUT"
echo ""
echo "✅ Готово: Podruga-установщик.zip на Рабочем столе. Отправляй другу."
read -r -p "Enter — закрыть"
