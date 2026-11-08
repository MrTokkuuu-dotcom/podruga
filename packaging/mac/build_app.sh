#!/bin/zsh
# Собирает самостоятельное «Подруга.app»: свой Python и все библиотеки внутри, подпись, проверка.
#   zsh packaging/mac/build_app.sh                      — подпись «на себя» (для проверки на этом Mac)
#   zsh packaging/mac/build_app.sh "Developer ID Application: Имя (TEAMID)"   — настоящая подпись
# Результат: ~/Podruga/dist/Подруга.app
set -euo pipefail
IDENTITY="${1:--}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$REPO/packaging/mac"
OUT="$HOME/Podruga/dist"
APP="$OUT/Подруга.app"
PYSRC="$(ls -d "$HOME/.local/share/uv/python/cpython-3.11."*-macos-aarch64-none | sort -V | tail -1)"
UV="$HOME/Podruga/bin/uv"
VERSION="$(cat "$REPO/VERSION")"

echo "▶ 1/6 Каркас приложения (версия $VERSION)"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$REPO/avatar/icon.icns" "$APP/Contents/Resources/icon.icns"
cp "$HERE/start.py" "$APP/Contents/Resources/start.py"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Подруга</string>
  <key>CFBundleDisplayName</key><string>Подруга</string>
  <key>CFBundleIdentifier</key><string>app.podruga.companion</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>CFBundleShortVersionString</key><string>1.$VERSION</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>Podruga</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>LSArchitecturePriority</key><array><string>arm64</string></array>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSAppNapIsDisabled</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>Чтобы слышать, когда ты со мной говоришь.</string>
  <key>NSAppleEventsUsageDescription</key><string>Чтобы открывать сайты и программы по твоей просьбе.</string>
</dict>
</plist>
PLIST

echo "▶ 2/6 Запускалка"
clang -O2 -arch arm64 -mmacosx-version-min=12.0 -o "$APP/Contents/MacOS/Podruga" "$HERE/launcher.c"

echo "▶ 3/6 Свой Python ($(basename "$PYSRC"))"
cp -R "$PYSRC" "$APP/Contents/Resources/python"
rm -f "$APP/Contents/Resources/python/lib/python3.11/EXTERNALLY-MANAGED"

echo "▶ 4/6 Библиотеки (из кэша — быстро)"
"$UV" pip install --quiet --python "$APP/Contents/Resources/python/bin/python3.11" -r "$REPO/requirements.txt"
# лишнее для работы: тесты, заголовки, кэш байткода
find "$APP/Contents/Resources/python" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "$APP/Contents/Resources/python" -path "*/site-packages/*/tests" -type d -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$APP/Contents/Resources/python/include" "$APP/Contents/Resources/python/share"
# заранее готовим .pyc и подписываем их вместе с приложением: тогда Python их только читает,
# а не пишет внутрь (запись внутрь ломает подпись)
"$APP/Contents/Resources/python/bin/python3.11" -m compileall -q -j 0 "$APP/Contents/Resources/python/lib" >/dev/null 2>&1 || true

echo "▶ 5/6 Код на первый запуск"
mkdir -p "$APP/Contents/Resources/app-seed"
(cd "$REPO" && git archive HEAD) | tar -x -C "$APP/Contents/Resources/app-seed"
rm -rf "$APP/Contents/Resources/app-seed/packaging" "$APP/Contents/Resources/app-seed/avatar/tools"

echo "▶ 6/6 Подпись ($IDENTITY)"
SIGN=(codesign --force --timestamp --options runtime --entitlements "$HERE/entitlements.plist" --sign "$IDENTITY")
[ "$IDENTITY" = "-" ] && SIGN=(codesign --force --options runtime --entitlements "$HERE/entitlements.plist" --sign -)
# сначала всё внутреннее (библиотеки и программы), потом само приложение
find "$APP/Contents/Resources/python" -type f \( -name "*.so" -o -name "*.dylib" -o -perm -111 \) -print0 |
  while IFS= read -r -d '' f; do
    if file -b "$f" | grep -q "Mach-O"; then "${SIGN[@]}" "$f" >/dev/null 2>&1 || echo "   не подписался: $f"; fi
  done
"${SIGN[@]}" "$APP/Contents/MacOS/Podruga"
"${SIGN[@]}" "$APP"
codesign --verify --deep --strict "$APP" && echo "   подпись в порядке"
du -sh "$APP"
echo "✅ Готово: $APP"
