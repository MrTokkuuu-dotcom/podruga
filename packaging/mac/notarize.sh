#!/bin/zsh
# Настоящая подпись + проверка Apple (нотаризация) + установочный образ .dmg.
# Нужно один раз (делает владелец аккаунта, вручную):
#   1) сертификат «Developer ID Application» в Связке ключей;
#   2) xcrun notarytool store-credentials podruga --apple-id ПОЧТА --team-id TEAMID
#      (спросит пароль приложения с appleid.apple.com — вводится руками, в Связку ключей).
# Запуск:  zsh packaging/mac/notarize.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$HOME/Podruga/dist"
APP="$OUT/Подруга.app"
PROFILE="${PROFILE:-podruga}"
IDENTITY="${IDENTITY:-$(security find-identity -v -p codesigning | grep -o '"Developer ID Application: [^"]*"' | head -1 | tr -d '"')}"
[ -n "$IDENTITY" ] || { echo "❌ Нет сертификата «Developer ID Application» в Связке ключей."; exit 1; }
VERSION="$(cat "$REPO/VERSION")"
DMG="$OUT/Podruga-1.$VERSION.dmg"

echo "▶ Сборка и подпись: $IDENTITY"
zsh "$REPO/packaging/mac/build_app.sh" "$IDENTITY"

echo "▶ Проверка Apple для приложения (5–30 минут)"
ZIP="$OUT/Podruga-notarize.zip"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"
xcrun notarytool submit "$ZIP" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$APP"
rm -f "$ZIP"

echo "▶ Установочный образ"
rm -f "$DMG"
STAGE="$OUT/dmg-stage"
rm -rf "$STAGE"; mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Подруга" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"
codesign --force --timestamp --sign "$IDENTITY" "$DMG"
xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$DMG"

echo "▶ Проверка, как увидит покупатель"
spctl -a -vv "$APP"
spctl -a -vv -t open --context context:primary-signature "$DMG"
echo "✅ Готово: $DMG"
