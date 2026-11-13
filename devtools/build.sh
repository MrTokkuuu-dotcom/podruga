#!/bin/zsh
# Сборка 3D после правки avatar/vrm3d_src.js (и avatar/anims.json) + копия страницы для проверок без экрана.
#   T=/путь/к/инструментам zsh devtools/build.sh
# В $T должны быть: node (папка node-v22.11.0-darwin-arm64) и build/ с three@0.170.0, @pixiv/three-vrm@3.3.3, esbuild.
# Установка инструментов — в devtools/README.md.
set -e
T="${T:?укажи T — папку с инструментами}"
R="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$T/node-v22.11.0-darwin-arm64/bin:$PATH"
cd "$T/build" && cp "$R/avatar/vrm3d_src.js" "$R/avatar/anims.json" . \
  && npx esbuild vrm3d_src.js --bundle --minify --format=iife --target=safari15 --outfile="$R/avatar/vrm3d.js" 2>&1 | grep -vE 'Done|^$|vrm3d.js +[0-9]' || true
cd "$R" && python3 avatar/build_app_html.py
# страница для Playwright: python3 -m http.server 8766 в $T/site
rm -rf "$T/site"; mkdir "$T/site"; cp -R "$R/avatar/." "$T/site/"
ln -sf "$HOME/Podruga/avatar.vrm" "$T/site/model.vrm"
