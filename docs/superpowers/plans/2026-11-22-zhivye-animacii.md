# Живые анимации — план работ

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Подруга ощущается живой девушкой с весом: женственная посадка (ничего не видно под юбкой), руки без дрожи и не сквозь одежду, живые пальцы и ступни, кончики волос, тихие звуки — в анимешном стиле.

**Architecture:** Основа `avatar/vrm3d_src.js` остаётся (микшер клипов, своя поза стоя, `pose()` → пружины → кости). Новые слои — отдельные модули `avatar/anim/*.js`, которые `vrm3d_src.js` вызывает в фиксированных местах кадра. Проверки — скрипт Playwright `devtools/anim_check.py` с числовыми порогами (у 3D нет модульных тестов), Python-часть — `unittest`.

**Tech Stack:** three.js 0.170.0, @pixiv/three-vrm 3.3.3, esbuild (target safari15), Web Audio API, Python 3.11, pywebview 6.2.1, Playwright + Chromium swiftshader.

**Spec:** `docs/superpowers/specs/2026-11-22-zhivye-animacii-design.md`

## Global Constraints
- Править только в `~/Podruga/podruga-repo`; проверка у Димы — `rsync -a --exclude .git --exclude __pycache__ --exclude avatar/model.vrm podruga-repo/ app/` и `open /Applications/Подруга.app` (restart.flag у Claude не перезапускает).
- Сборка 3D — `T=<папка инструментов> zsh devtools/build.sh`; инструменты ставятся в scratchpad по `devtools/README.md`, не в репо.
- Частота кадров не меняется: покой 20, взгляд 30, движение/разговор 60, сон 8 (`wantFps`). Новые слои не поднимают её.
- Нагрузка: покой — не больше +2–3% одного ядра к v26 (≈33–37% сумма), в движении — не больше +5%.
- Поза сидя на полу — только боком, ноги вместе. «Обняла колени» и сэйдзу не делать.
- Звуки — только CC0 (или явно разрешающая продажу лицензия), каждый файл записан в `THIRD_PARTY.md`.
- Не сломать: ходьба по окнам, прыжки, сон/ложится, касания, переодевание, да/нет, клики насквозь.
- Никогда не коммитить `.env`, `data/`, `avatar/model.vrm`, ключи. Выпуск (VERSION +1 → commit → push main) — только после «да» Димы в чате.
- Все пороги проверок — для всех моделей в `~/Podruga/avatars/*/*.vrm`.

## Review Focus
1. **Длинная юбка/пальто + сидит боком** — подол проходит сквозь бедро или задирается. Ожидание: подол лежит поверх ног. → проверка `skirt_through_legs` в Task 1.
2. **Окно закрыли/сдвинули, пока она садится на край** — ноги остаются в позе «на краю» в воздухе. Ожидание: плавно встаёт и падает как сейчас. → проверка `edge_fall_midsit` в Task 3.
3. **Переодели или сменили девочку, пока сидит/идёт** — новая модель стартует в сломанной позе, IK держит ступни в старых точках. Ожидание: новая модель в той же позе без рывка, якоря ступней сброшены. → проверка `reload_while_sitting` в Task 6.
4. **Смена частоты кадров 60→20→8** — ступни «щёлкают», руки вздрагивают. Ожидание: никаких скачков. → проверка `fps_switch_pop` в Task 4 (руки) и Task 7 (ступни).
5. **Окно спрятано / пауза в игре / человек начал говорить посреди шага** — звук всё равно играет. Ожидание: тишина. → проверки `sound_hidden`, `sound_quiet` в Task 10.

---

## Структура файлов
| Файл | Отвечает за |
|---|---|
| `avatar/anim/keyposes.js` (новый) | ключевые позы и переходы: сидит боком, на край окна, присед перед прыжком; функция «позы по времени» |
| `avatar/anim/hands.js` (новый) | формы кистей (пальцы) по позе + лёгкое движение пальцев |
| `avatar/anim/weight.js` (новый) | вес: якоря ступней + IK двух костей, перекат пятка→носок, качание таза на шаге, перенос веса стоя, подготовка/дотяг |
| `avatar/anim/sounds.js` (новый) | Web Audio: загрузка звуков, шаги/приземление/шорох, разброс, тишина по команде |
| `avatar/sounds/*.ogg` (новые) | CC0-звуки |
| `avatar/vrm3d_src.js` | вызов слоёв в `pose()`/`tick()`, исправленный `avoidBody()`, волосы в `tunePhysics()`, новые методы `VRM3D` |
| `devtools/build.sh` | копировать `avatar/anim/` в папку сборки |
| `devtools/anim_check.py` (новый) | все проверки: `python anim_check.py SITE OUT [имя_проверки…]`, печатает PASS/FAIL, код выхода 1 при FAIL |
| `devtools/test_sounds_py.py` (новый) | unittest Python-части звуков |
| `avatars.json` | у нарядов поле `bulk` (запас одежды, м) |
| `config.py`, `ui.py`, `main.py`, `avatar/app_template.html` | настройка «Звуки», мост страница↔Python для звуков |
| `THIRD_PARTY.md` (новый) | источники и лицензии звуков |

---

### Task 0: Инструменты, сборка модулей и скрипт проверок

**Files:**
- Modify: `devtools/build.sh` (строка `cp "$R/avatar/vrm3d_src.js" …`)
- Create: `devtools/anim_check.py`
- Modify: `devtools/README.md` (раздел «Скрипты»)

**Interfaces:**
- Produces: `anim_check.py` — реестр `CHECKS: dict[str, Callable[[Page, str], tuple[bool, str]]]` (страница, имя модели → прошло, пояснение); общие помощники `load(page, model_path)`, `step(page, n, dt)`, `shot(page) -> PIL.Image`, `bones(page) -> dict` (через `VRM3D._w()`); запуск всех или выбранных проверок по всем моделям; лист кадров `OUT/<проверка>.png`; файл `OUT/baseline.json` с числами.
- Produces: декоратор `@check("имя")` — так последующие задачи добавляют проверки.

- [ ] **Step 1:** Поставить node 22.11.0, esbuild, three@0.170.0, @pixiv/three-vrm@3.3.3, Playwright+Chromium в `$T` = scratchpad/tools по `devtools/README.md`. Проверка: `$T/node-v22.11.0-darwin-arm64/bin/node -v` → `v22.11.0`.
- [ ] **Step 2:** В `build.sh` после копирования `vrm3d_src.js` добавить `rm -rf anim && cp -R "$R/avatar/anim" .` (папка создаётся пустой с `.gitkeep`, пока модулей нет). Проверка: `T=$T zsh devtools/build.sh` без ошибок, `avatar/vrm3d.js` пересобран.
- [ ] **Step 3:** Написать `anim_check.py` с реестром и первыми «замерами как есть» (не проверками): `jitter_now` (максимальный сдвиг кисти между кадрами в покое за 3 с при 20/30/60 кадрах, мм), `foot_slide_now` (сдвиг опорной ступни в мире за шаг, см), `armhits_now` (`_armHits()` по позам clasp/foldArms/think/behind/hip), `skirt_now` (кадры сидя спереди-снизу). Числа → `OUT/baseline.json`.
- [ ] **Step 4:** Запуск: `cd $T/site && python3 -m http.server 8766 &` и `$T/pw/bin/python devtools/anim_check.py $T/site $OUT`. Ожидание: baseline.json со всеми моделями; лист `skirt_now.png` показывает текущую проблему (видно под юбкой) — это «до».
- [ ] **Step 5:** Commit `devtools: animation check harness and module build` (без выпуска).

---

## Выпуск A (v28) — посадка

### Task 1: Ключевые позы и сидит боком на полу

**Files:**
- Create: `avatar/anim/keyposes.js`
- Modify: `avatar/vrm3d_src.js` — `SIT_POSE` (стр. ~468), `mixerStep()` ветка `S.sitting` (стр. ~426), `pose()` блок `sitK` (стр. ~541), `pose()` применение ног (стр. ~620–641: добавить оси `z`/`y` для бёдер и `hipsY`)
- Test: `devtools/anim_check.py`

**Interfaces:**
- Produces: `export function keyAt(keys, k, base) -> {P, extra}` — то же, что `lieAt`, обобщённо: `keys = [{k, P, roll?}]`, `smooth`-интерполяция, недостающие поля из `base`.
- Produces: `export const SIDE_SIT_KEYS` (вход: 0 → присела коленями вместе → опора на руку → бёдра на пол → ноги уложены на одну сторону), `export const SIDE_SIT_POSE` (итог), `export const SIDE_SIT_EXIT_KEYS`.
- Produces: новые поля позы `lLegZ, rLegZ, lLegY, rLegY` (сведение/поворот бедра) и `hipsYaw`, `hipsRoll` — применяются в `pose()` наравне с `lLegX`.
- Сторона ног (`S.sitSide = ±1`) выбирается при каждой посадке: в сторону, противоположную направлению последнего шага, чтобы ноги не были «к нам».

- [ ] **Step 1:** Добавить проверку `@check("skirt_side_sit")`: для каждой модели посадка (`VRM3D.sit(true)`, 4 с по 1/60), камера с 3 точек (спереди, спереди-снизу −15°, спереди-снизу −30°). Проход, если в прямоугольнике между бёдрами ниже подола нет пикселей цвета кожи/белья: по маске — пиксели внутри силуэта, не принадлежащие мешам одежды. Реализация маски: рендер второй раз с материалами одежды = чёрный, тела = белый (`VRM3D._mask(true)` — новый хук, перекрашивает меши по имени: `Body`/`Face` белым, остальное чёрным); доля белого в треугольнике «от колен до таза» < 0,5%.
- [ ] **Step 2:** Запустить `anim_check.py … skirt_side_sit` → FAIL на всех моделях с юбкой (текущая поза).
- [ ] **Step 3:** Реализовать `keyposes.js` и заменить посадку: сидя на полу `mixerStep` больше не включает `sitEnter/sitIdle/sitTalk/sitExit` (они остаются только для края окна до Task 3), ноги и таз — из `keyAt(SIDE_SIT_KEYS, k)`, `k = clamp01(S.downT / 1.6)`; вставание — `SIDE_SIT_EXIT_KEYS` за 1,3 с. Анимешный характер: в ключе «бёдра на пол» таз чуть ниже итога (+0,015 м проседание) и возврат — «доседает». Голова/руки как сейчас (оглядывается). `SEAT_Y` пересчитать под позу боком (таз на полу, ничего ниже пола — проверка `_w().hips[1] >= 0.1`).
- [ ] **Step 4:** Запустить `skirt_side_sit` → PASS на всех моделях. Добавить в проверку `@check("skirt_through_legs")`: точки подола (spring-кости `Skirt`) не внутри капсул бёдер (`intoCapsule` < 1 см) — PASS. Если подол проходит — капсулы ног в `tunePhysics()` следуют за новой позой (они на костях — проверить радиус 0,085→0,095).
- [ ] **Step 5:** Посмотреть лист `skirt_side_sit.png` и кадры перехода (12 кадров посадки) глазами; сохранить видео 4 с (`OUT/sit.webm`, запись Playwright).
- [ ] **Step 6:** Commit `v28 wip: side sit with legs together`.

### Task 2: Ложится из положения сидя и сон

**Files:**
- Modify: `avatar/vrm3d_src.js` — `updatePosture()` (стр. ~371–401), `layStep()`
- Test: `devtools/anim_check.py`

**Interfaces:**
- Consumes: `SIDE_SIT_POSE`, `keyAt` (Task 1).

- [ ] **Step 1:** Проверка `@check("sit_to_lie")`: сесть (4 с), затем `VRM3D.lie(true)` 8 с, затем `lie(false)` 8 с. Проход: ни в одном кадре нет скачка кости > 0,08 рад между соседними кадрами (60 кадров/с) и таз не ниже 0,1 м; итог — стоит (`pos().posture == 'stand'`, `sitK == 0`).
- [ ] **Step 2:** Запустить → FAIL ожидаем на переходе (клип `layUp` стартует из стоя).
- [ ] **Step 3:** Если сидит и просят лечь — сначала `SIDE_SIT_EXIT_KEYS` до положения «на коленях вместе» (k=0.4), затем `layUp` задом наперёд с того же кадра (смешать за 0,4 с). Сон по шагам (`sleepSeq('down')`) идёт тем же путём.
- [ ] **Step 4:** Запустить `sit_to_lie` и `skirt_side_sit` → PASS.
- [ ] **Step 5:** Commit `v28 wip: lie down from side sit`.

### Task 3: Край окна и присед перед прыжком — колени вместе

**Files:**
- Modify: `avatar/anim/keyposes.js` (добавить `EDGE_SIT_KEYS`, `EDGE_SIT_POSE`, `CROUCH_ADD`)
- Modify: `avatar/vrm3d_src.js` — ветка `S.edge` в `updatePosture()`/`pose()`, `jumpStep()`/`mixerStep()` фаза `crouch`/`land`
- Test: `devtools/anim_check.py`

**Interfaces:**
- Produces: `EDGE_SIT_POSE` — колени вместе (`lLegZ/rLegZ` сведены, щиколотки скрещены), руки ладонями на край по бокам; лёгкое болтание голенями `sin(t·1.3)` амплитуда 0,12 рад, ноги в противофазе, раз в 6–12 с пауза.
- Produces: `CROUCH_ADD` — добавка к клипам `jumpStart`/`jumpLand`: бёдра сведены (z), одна рука к подолу (кисть у бедра спереди) при весе приседа.

- [ ] **Step 1:** Проверки `@check("skirt_edge_sit")` (как `skirt_side_sit`, поза на краю: `VRM3D.ledges([[1,200,900,400]])`, `jumpTo`, `sitEdge(true)`), `@check("skirt_crouch")` (кадры фаз `crouch` и `land` прыжка), `@check("edge_fall_midsit")` (посреди посадки на край `ledges([])` → через 3 с `pos().support == null`, стоит на полу, нет скачков > 0,08 рад).
- [ ] **Step 2:** Запустить → FAIL `skirt_edge_sit`, `skirt_crouch`.
- [ ] **Step 3:** Край: заменить клипы `sitEnter/sitIdle` на `EDGE_SIT_KEYS` (вход 1,2 с) и `EDGE_SIT_POSE`; клипы `sit*` удалить из `mixerStep` совсем. Прыжок: накладывать `CROUCH_ADD` с весом клипа `jumpStart`/`jumpLand`.
- [ ] **Step 4:** Запустить все `skirt_*`, `edge_fall_midsit`, `sit_to_lie` → PASS. `models_check.py` (старая проверка) — без новых ошибок.
- [ ] **Step 5:** Живая проверка у Димы (rsync + открыть приложение): посадка на полу, на краю окна, прыжок. Видео/скриншоты → Диме, правки по отзыву.
- [ ] **Step 6:** После «да» Димы: VERSION=28, `git add -A avatar devtools docs && git commit -m "v28: feminine sitting — side sit, edge sit and crouch with knees together"` → push main.

---

## Выпуск B (v29) — руки и пальцы

### Task 4: Руки не дрожат

**Files:**
- Modify: `avatar/vrm3d_src.js` — `avoidBody()` (стр. ~746–780), пружины рук в `pose()` (`fArm`, стр. ~624)
- Test: `devtools/anim_check.py`

**Interfaces:**
- `avoidBody()` сохраняет имя и место; меняется только логика толчка.

- [ ] **Step 1:** Проверки `@check("hand_jitter")`: по позам rest/clasp/foldArms/think/behind/hip/elbow/hips2/headBehind/heart/cheek, сидя, на краю — 3 с при dt 1/20, 1/30, 1/60: «дрожь» = максимум модуля второй разности позиции кисти (мм/кадр²) после первых 2 с. Порог < 0,3 мм. `@check("fps_switch_pop")`: в покое переключать dt 1/60→1/20→1/8 каждые 0,5 с; скачок кисти между кадрами < 3 мм.
- [ ] **Step 2:** Запустить → FAIL (записать числа «до»).
- [ ] **Step 3:** Толчок от тела — одна пружина `spring('pushF_'+side, target, 3, 1.0)` к цели `target = глубина·k` с гистерезисом: цель растёт при входе (margin 0,02), сбрасывается только когда точка дальше 0,06 м (зона «near» больше не держит и не отпускает по кругу). Затухание z=1.0 (без перелёта). Применение к `up.rotation` — один раз в кадре.
- [ ] **Step 4:** Запустить `hand_jitter`, `fps_switch_pop`, `armhits_now` (как проверку: 0 точек) → PASS.
- [ ] **Step 5:** Commit `v29 wip: no arm jitter`.

### Task 5: Руки не сквозь одежду

**Files:**
- Modify: `avatars.json` (у каждого наряда `"bulk": <м>`; по умолчанию 0)
- Modify: `ui.py` `Api.ui_ready` (передать `bulk` текущего наряда вместе с persona)
- Modify: `avatar/vrm3d_src.js` — `intoBody(p, margin)` вызовы в `avoidBody()` (margin = 0,02 + bulk), новый `VRM3D.clothes(bulk)`
- Test: `devtools/anim_check.py`

**Interfaces:**
- Produces: `VRM3D.clothes(bulk: number)`; в `ui` страницы — `ui.clothes(b)`; Python шлёт `self._call("clothes", bulk)` сразу после `persona`.
- Значения: худи (Аня `cozy`) 0,045; пальто/тренч (Таня `street2`) 0,04; свитер (Таня `cozy`) 0,03; джинсовая куртка (Аня `spring`) 0,03; остальные 0,01. Подобрать по проверке.

- [ ] **Step 1:** Проверка `@check("arms_through_clothes")`: для каждой модели — позы из `hand_jitter`; точки руки (кисть, локоть, середина предплечья) не внутри меша одежды: луч из точки к оси позвоночника не пересекает меш одежды нечётное число раз (`THREE.Raycaster` по мешам не `Body`/`Face`/`Hair`, хук `VRM3D._clothHits()`). Порог: 0.
- [ ] **Step 2:** Запустить → FAIL на худи/пальто.
- [ ] **Step 3:** Реализовать `bulk`, подобрать значения по моделям до PASS.
- [ ] **Step 4:** Запустить `arms_through_clothes`, `hand_jitter` → PASS.
- [ ] **Step 5:** Commit `v29 wip: arms clear bulky clothes`.

### Task 6: Живые пальцы

**Files:**
- Create: `avatar/anim/hands.js`
- Modify: `avatar/vrm3d_src.js` — в `pose()` после применения рук, до `avoidBody()`
- Test: `devtools/anim_check.py`

**Interfaces:**
- Produces: `export const HAND_SHAPES = { relax, clasp, fist, hair, skirt, edge, cheek, heart, chin }` — для каждой: изгиб пальцев `{thumb, index, middle, ring, little}` (рад на сустав, три сустава с коэффициентами 1, 0.9, 0.7) и развод `spread`.
- Produces: `export function applyHands(bone, shapeL, shapeR, w, t)` — плавный переход формы (пружина f=3), «дыхание» пальцев ±0,04 рад с разной фазой, только кости `left/right{Thumb,Index,Middle,Ring,Little}{Metacarpal|Proximal,Intermediate,Distal}`.
- Produces: таблица «поза → форма» (`POSE_HANDS`): rest→relax, clasp/pat→clasp, happy→fist, hair/headBehind→hair, think→chin, cheek→cheek, heart→heart, сидит боком/край→edge, присед→skirt (одна рука), shy→clasp.
- Сброс при перезагрузке модели: пружины пальцев и якоря ступней (Task 7) обнуляются в `init()`.

- [ ] **Step 1:** Проверки `@check("fingers_alive")`: в rest средний изгиб `indexProximal` 0,2–0,5 рад, за 4 с меняется > 0,01 рад; в `happy` изгиб > 1,2 рад; нет NaN. `@check("reload_while_sitting")`: сидит → `VRM3D.start(model)` заново → через 2 с поза сидя, нет NaN, кисти с формой `edge`.
- [ ] **Step 2:** Запустить → FAIL.
- [ ] **Step 3:** Реализовать `hands.js` и подключить.
- [ ] **Step 4:** Запустить `fingers_alive`, `reload_while_sitting`, `arms_through_clothes`, `hand_jitter` → PASS. Лист крупных планов кистей по формам — глазами.
- [ ] **Step 5:** Живая проверка у Димы, правки. После «да»: VERSION=29, commit `v29: steady hands, arms clear clothes, living fingers` → push.

---

## Выпуск C (v30) — вес, ступни, волосы

### Task 7: Ступни на полу — якоря и IK, перекат пятка→носок

**Files:**
- Create: `avatar/anim/weight.js`
- Modify: `avatar/vrm3d_src.js` — `tick()` (после `pose()`, перед `vrm.update`), `mixerStep()` (фаза шага уже есть: `sm.walkPh`)
- Test: `devtools/anim_check.py`

**Interfaces:**
- Produces: `export function createWeight(bone) -> W` с методами `W.reset()`, `W.update(dt, ctx)`, `W.events` (массив событий кадра `{type: 'step'|'land', foot: 'left'|'right', strength: 0..1}` — для звуков в Task 10).
- `ctx = { walkPh, walkW, standing, sitK, edgeK, layW, jump, floorY: 0, yaw }`.
- IK: аналитическая двух костей (`UpperLeg`, `LowerLeg`), колено в плоскости, направленной вперёд модели; работает только при `standing` или `walkW > 0` и `layW < 0.5`, `sitK == edgeK == 0`.
- Якорь опорной ступни: ставится в момент касания (фаза клипа, где ступня ниже всего), держится до отрыва; ступня в опоре горизонтальна; на отрыве — носок (`Toes`) сгибается до 0,5 рад, пятка поднимается раньше носка; при касании — пятка первой (ступня `x` −0,25 рад → 0).

- [ ] **Step 1:** Проверки `@check("foot_slide")`: ходьба 6 с со скоростью 60 и 120 px/с; смещение ступни в мире за всю опору < 1 см. `@check("toe_roll")`: на отрыве `leftToes.rotation.x` > 0,3 рад. `@check("fps_switch_pop")` дополнить ступнями (скачок < 3 мм). Обновить `reload_while_sitting`: после перезагрузки якоря пустые.
- [ ] **Step 2:** Запустить → FAIL `foot_slide`, `toe_roll`.
- [ ] **Step 3:** Реализовать якоря, IK и перекат.
- [ ] **Step 4:** Запустить `foot_slide`, `toe_roll`, `fps_switch_pop`, `reload_while_sitting`, все `skirt_*` → PASS.
- [ ] **Step 5:** Commit `v30 wip: planted feet with heel-toe roll`.

### Task 8: Вес тела — таз на шаге, перенос веса стоя, подготовка и дотяг

**Files:**
- Modify: `avatar/anim/weight.js`
- Modify: `avatar/vrm3d_src.js` — `pose()` блок «стоит: еле заметно переносит вес» (стр. ~530) заменяется; события старт/стоп ходьбы и приземления из `stageMove()`/`jumpStep()`
- Test: `devtools/anim_check.py`

**Interfaces:**
- Consumes: `W` из Task 7 (IK держит ступни при смещении таза).
- Produces: в `W.update` — смещение таза: на шаге опускание 1,5 см (дважды за цикл) + наклон в сторону опорной ноги 0,04 рад; стоя — вес на одной ноге: таз в сторону 2,5 см, наклон 0,05 рад, другое колено согнуто 0,15 рад; смена ноги раз в 6–14 с за 0,9 с (`PERSONA.pace` масштабирует).
- Produces: `W.impulse(kind)` — `'start'` (подготовка: таз −1 см и корпус назад 0,04 рад за 0,15 с), `'stop'` (дотяг: корпус вперёд 0,05 рад, возврат пружиной f=2,2 z=0,45), `'land'` (таз −3 см, колени), `'sit'` (проседание из Task 1 — перенести сюда).

- [ ] **Step 1:** Проверки `@check("walk_bob")`: на ходу колебание `hips.y` с частотой 2 на цикл шага, размах 1–2,5 см. `@check("weight_shift")`: стоя 30 с — минимум одна смена опорной ноги, ступни в это время сдвигаются < 5 мм, `hips.x` отклоняется 1,5–3,5 см. `@check("settle_after_stop")`: после `walkStop()` наклон корпуса вперёд > 0,02 рад и возврат < 0,005 рад за 1,5 с. `@check("land_dip")`: после приземления `hips.y` ниже покоя на 2–4 см в течение 0,1–0,3 с.
- [ ] **Step 2:** Запустить → FAIL.
- [ ] **Step 3:** Реализовать.
- [ ] **Step 4:** Запустить все проверки задач 1–8 → PASS. Записать видео ходьбы/остановки/прыжка 10 с — глазами (не «кукла», не «желе»).
- [ ] **Step 5:** Commit `v30 wip: body weight`.

### Task 9: Кончики волос

**Files:**
- Modify: `avatar/vrm3d_src.js` — `tunePhysics()` (стр. ~884)
- Test: `devtools/anim_check.py`

**Interfaces:**
- В `tunePhysics()`: для цепочек `J_Sec_Hair*` — последние 2 сустава цепочки: `stiffness ×0.55`, `dragForce = 0.35`, `gravityPower` как было; остальные не трогать.

- [ ] **Step 1:** Проверка `@check("hair_tips")`: на ходу (6 с) кончик самой длинной цепочки отклоняется относительно головы > 1,5 см больше, чем стоя; корень цепочки — разница < 3 мм; через 2 с после остановки кончик успокаивается (скорость < 2 мм/кадр).
- [ ] **Step 2:** Запустить → FAIL.
- [ ] **Step 3:** Реализовать.
- [ ] **Step 4:** Запустить → PASS; волосы не проходят сквозь голову (визуально, лист кадров).
- [ ] **Step 5:** Замер нагрузки (как в v26: обвязка `devtools/e2e_av.py`, минута по ps time) в покое/взгляде/сне/на ходу — сравнить с v26, должно уложиться в Global Constraints. Живая проверка у Димы. После «да»: VERSION=30, commit `v30: weight, planted feet, hair tips` → push.

---

## Выпуск D (v31) — звуки

### Task 10: Звуки в странице

**Files:**
- Create: `avatar/anim/sounds.js`, `avatar/sounds/` (шаги ×6, шаги по окну ×4, приземление ×2, шорох ×4), `THIRD_PARTY.md`
- Modify: `avatar/vrm3d_src.js` — `tick()` (раздать `W.events`), посадка/потягивание (`act-stretch`, `act-yawn`) — шорох; `VRM3D.sounds(on)`, `VRM3D.quiet(on)`
- Modify: `avatar/build_app_html.py` и `devtools/build.sh` — папка `sounds/` рядом с `app.html`
- Test: `devtools/anim_check.py`

**Interfaces:**
- Produces: `export function createSounds(baseUrl) -> Snd` — `Snd.play(kind, strength)` (`kind`: `step`, `stepLedge`, `land`, `rustle`), `Snd.enabled`, `Snd.quiet`; разброс: высота ±6%, громкость ±20%, не повторять один файл подряд; общая громкость 0,25.
- Не играет, если `!enabled`, `quiet`, `document.hidden`, или прошло < 0,12 с с прошлого звука того же вида.
- После каждого звука: `window.pywebview.api.own_sound(dur_s)`.
- `AudioContext` закрывается (`suspend()`) через 2 с без звуков — чтобы CoreAudio не считал, что Mac играет звук.
- Звуки: Kenney (CC0) — «Impact Sounds» (шаги, приземление), «RPG Audio» (шорох ткани); каждый файл → `THIRD_PARTY.md` (имя, набор, ссылка, CC0).

- [ ] **Step 1:** Проверки `@check("sound_events")` (ходьба 6 с — число вызовов `play('step')` = числу касаний ступней ±1, перехват через `VRM3D._sndLog()`), `@check("sound_hidden")` (`document.hidden` эмулировать: `Object.defineProperty(document,'hidden',{value:true})` → 0 звуков), `@check("sound_quiet")` (`VRM3D.quiet(true)` → 0 звуков), `@check("sound_off")` (`sounds(false)` → 0).
- [ ] **Step 2:** Запустить → FAIL.
- [ ] **Step 3:** Скачать наборы Kenney в новую пустую папку scratchpad, выбрать файлы, перекодировать в ogg (≤ 30 КБ каждый), положить в `avatar/sounds/`, записать `THIRD_PARTY.md`. Реализовать `sounds.js`.
- [ ] **Step 4:** Запустить звуковые проверки → PASS.
- [ ] **Step 5:** Commit `v31 wip: footstep and cloth sounds in page`.

### Task 11: Звуки и слух, настройка «Звуки»

**Files:**
- Modify: `config.py` (`USER_KEYS` + `"sounds"`, по умолчанию `"1"`), `apply_user_settings` → `cfg["sounds"]`
- Modify: `ui.py` — `Api.own_sound(sec)`, `get_settings` (+`sounds`), `ui_ready` → `self._call("sounds", on)`
- Modify: `main.py` — `other_audio()` (стр. 202), `on_phrase()` (стр. 785), состояние «человек говорит»/пауза → `ui.quiet`
- Modify: `audio_in.py` — колбэк начала речи (`triggered = True`, стр. ~191) вызывает `on_speech_start`, конец — `on_speech_end`
- Modify: `avatar/app_template.html` — галочка «Звуки (шаги, шорох)» в настройках, `ui.sounds`, `ui.quiet`, `ui.clothes`
- Test: `devtools/test_sounds_py.py`

**Interfaces:**
- Consumes: `api.own_sound(dur_s)` из Task 10.
- Produces: `Companion.own_sound(sec: float) -> None` — `self._own_end = max(self._own_end, now + sec + 0.15)`.
- Produces: `Companion.other_audio()` — `False` также пока `now < self._own_end + 1.0` (её звуки — не «Mac играет»).
- Produces: `Companion.on_phrase(wav)` — фраза отбрасывается, если она началась и закончилась внутри окна своего звука (`start >= own_start and end <= self._own_end`) и короче 0,6 с.
- Produces: `listener.on_speech_start/on_speech_end` → `ui.quiet(True/False)`; пауза (`pauser.paused`) и сон с закрытым окном → `ui.quiet(True)`.

- [ ] **Step 1:** Написать `test_sounds_py.py` (unittest, без микрофона: `Companion` собирается с заглушками как в `devtools/e2e_av.py` или тестируются вынесенные функции `own_window(now, own_end) -> bool`, `drop_phrase(start, end, own_start, own_end) -> bool`): `test_other_audio_ignores_own_sound` (own_sound(0.3) → other_audio() == False 1 с, даже если `sysaudio.output_running` замокан в True), `test_short_phrase_inside_own_sound_dropped`, `test_long_phrase_overlapping_kept` (фраза 1,5 с, перекрывает звук — не отбрасывается), `test_settings_sounds_key_saved` (`save_user_settings({"sounds": "0"})` → `cfg["sounds"] == "0"`).
- [ ] **Step 2:** `~/Podruga/venv/bin/python -m unittest devtools/test_sounds_py.py -v` → FAIL.
- [ ] **Step 3:** Реализовать по Interfaces.
- [ ] **Step 4:** Тесты → PASS; `pyflakes` по изменённым файлам — без новых предупреждений (особенно «redefinition» — грабли с `her`).
- [ ] **Step 5:** Сквозная проверка `devtools/e2e_av.py` с фразами («привет подруга», «как дела», «иди погуляй», пока она идёт — «как дела» ещё раз): в журнале нет «похоже на музыку/шум» из-за её шагов, все фразы распознаны.
- [ ] **Step 6:** Commit `v31 wip: sounds don't disturb hearing, settings switch`.

### Task 12: Итог выпуска D и общая проверка

- [ ] **Step 1:** Все проверки `anim_check.py` по всем моделям → PASS; unittest → PASS; `models_check.py` — без новых ошибок.
- [ ] **Step 2:** Замер нагрузки до/после (v26 → v31) — таблица в `ПЕРЕДАЧА_ДЛЯ_НОВОГО_ЧАТА.md`.
- [ ] **Step 3:** Живая проверка у Димы: ходит, садится, на краю, прыжок, звуки вкл/выкл, говорит с ней во время ходьбы.
- [ ] **Step 4:** После «да»: VERSION=31, commit `v31: quiet footsteps and cloth sounds` → push; обновить `ПЕРЕДАЧА…` и «Где остановились» в CLAUDE.md.
