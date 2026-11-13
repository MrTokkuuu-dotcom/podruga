# Инструменты для разработки (Mac)

Ничего отсюда не нужно для работы «Подруги» — только для правок и проверок.

## Установка (один раз, в любую временную папку T)
```
T=/путь/к/папке; mkdir -p $T/build && cd $T
V=v22.11.0; curl -fsSLO https://nodejs.org/dist/$V/node-$V-darwin-arm64.tar.gz
curl -fsSL https://nodejs.org/dist/$V/SHASUMS256.txt | grep "node-$V-darwin-arm64.tar.gz" | shasum -a 256 -c - && tar xzf node-$V-darwin-arm64.tar.gz
export PATH=$T/node-$V-darwin-arm64/bin:$PATH
cd $T/build && npm init -y && npm i three@0.170.0 @pixiv/three-vrm@3.3.3 esbuild
cd $T && ~/Podruga/bin/uv venv --python 3.11 pw && ~/Podruga/bin/uv pip install --python pw/bin/python playwright pillow
PLAYWRIGHT_BROWSERS_PATH=$T/pwb pw/bin/python -m playwright install chromium
```
Анимации-исходники (CC0, нужны только чтобы заново переложить клипы `avatar/tools/retarget_ual.py`):
- https://opengameart.org/sites/default/files/universal_animation_librarystandard.zip
- https://opengameart.org/sites/default/files/universal_animation_library_2standard.zip

## Скрипты
- `build.sh` — собрать `avatar/vrm3d.js` и `avatar/app.html`, сделать копию страницы в `$T/site`.
- `models_check.py SITE OUT` — каждую модель из `~/Podruga/avatars`: загрузка, физика, руки в позах и на ходу,
  лист кадров `OUT/all_models.png`. Перед запуском: `cd $T/site && python3 -m http.server 8766`.
- `e2e_av.py APP HOME` — вся программа целиком (настоящее окно), вместо микрофона — синтез Silero; переодевает
  трёх девочек и снимает экран. Запускать из `~/Podruga/app`, HOME — временная папка (память Димы не трогает).
  Шаблон для любых живых проверок: в `SCRIPT` можно вписать фразы («привет подруга», «как дела»…) —
  в журнале будут строки `[время]` с задержками.

## Хуки 3D для проверок (в странице)
`VRM3D._freeze(true)`, `_step(n, dt)`, `_w()` (кости в мире), `_armHits()` (точки рук внутри тела),
`_noAvoid(on)`, `stage(true,W,H,x,y)`, `walkTo(x)`, `sleepSeq('down'|'cancel')`, `ledges([...])`, `jumpTo(x,y,id)`,
`sitEdge(on)`, `gesture('yes'|'no'|'foldArms')`, `idle(pose, sec)`.
Запуск Chromium: `--use-gl=swiftshader --enable-webgl --ignore-gpu-blocklist --enable-unsafe-swiftshader`.
