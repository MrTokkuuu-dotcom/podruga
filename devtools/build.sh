#!/bin/zsh
# Сборка 3D после правки avatar/vrm3d_src.js (и avatar/anims.json) + копия страницы для проверок без экрана.
#   T=/путь/к/инструментам zsh devtools/build.sh
# В $T должны быть: node (папка node-v22.11.0-darwin-arm64) и build/ с three@0.170.0, @pixiv/three-vrm@3.3.3, esbuild.
# Установка инструментов — в devtools/README.md.
set -e
T="${T:?укажи T — папку с инструментами}"
R="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$T/node-v22.11.0-darwin-arm64/bin:$PATH"
[ -x "$T/node-v22.11.0-darwin-arm64/bin/node" ] || { echo "ОШИБКА: нет node в $T (macOS мог почистить временную папку) — поставь заново, см. README"; exit 1; }
cd "$T/build" && cp "$R/avatar/vrm3d_src.js" "$R/avatar/anims.json" . && rm -rf anim && cp -R "$R/avatar/anim" .
npx esbuild vrm3d_src.js --bundle --minify --format=iife --target=safari15 --outfile="$R/avatar/vrm3d.js" --log-level=warning \
  || { echo "ОШИБКА: сборка 3D не удалась"; exit 1; }
cd "$R" && python3 avatar/build_app_html.py
# страница для Playwright: python3 -m http.server 8766 в $T/site
rm -rf "$T/site"; mkdir "$T/site"; cp -R "$R/avatar/." "$T/site/"
rm -rf "$T/site/anim"; ln -sf "$HOME/Podruga/avatar.vrm" "$T/site/model.vrm"
