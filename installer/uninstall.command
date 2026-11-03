#!/bin/bash
# Удаление «Подруги»: приложение, Python для неё, голоса. Память и ключ — по желанию.
H="$HOME/Podruga"
echo "Удалить «Подругу»? (y — да)"; read -r A; [ "$A" = "y" ] || exit 0
pkill -f "Podruga/venv/bin/python" 2>/dev/null; rm -rf "$HOME/Library/Application Support/Podruga"
rm -rf "/Applications/Подруга.app" "$HOME/Applications/Подруга.app" "$H/app" "$H/venv" "$H/bin" "$H/venv_cb" "$HOME/Library/LaunchAgents/com.podruga.companion.plist"
echo "Удалить и её память, переписку и ключ? (y — да, всё забыть)"; read -r B
[ "$B" = "y" ] && rm -rf "$H"
echo "Готово."; read -r -p "Enter — закрыть"
