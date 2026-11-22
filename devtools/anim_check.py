"""Проверки анимаций без экрана (Playwright + Chromium swiftshader).

    cd $T/site && python3 -m http.server 18767 &   (PORT=… — другой порт)
    $T/pw/bin/python devtools/anim_check.py $T/site OUT [проверка …]

MODELS=anya/default,tanya/formal — только эти модели (по умолчанию все из ~/Podruga/avatars).
Печатает PASS/FAIL по каждой модели, листы кадров — OUT/<проверка>.png, числа — OUT/results.json.
Код выхода 1, если хоть одна проверка не прошла. Замеры *_now — «как есть», всегда PASS.
"""
import base64
import io
import json
import math
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

AV = Path.home() / "Podruga" / "avatars"
PORT = int(os.environ.get("PORT", "18767"))
CHECKS = {}


def check(name):
    def deco(fn):
        CHECKS[name] = fn
        return fn
    return deco


# ---------- помощники ----------
def step(pg, n, dt=1 / 60):
    pg.evaluate(f"VRM3D._step({int(n)}, {dt})")


def shot(pg, label=""):
    b64 = pg.evaluate("(VRM3D._step(0), document.getElementById('vrmCanvas').toDataURL('image/png').split(',')[1])")
    im = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
    bg = Image.new("RGBA", im.size, (235, 235, 240, 255))
    bg.alpha_composite(im)
    if label:
        ImageDraw.Draw(bg).text((6, 6), label.encode("ascii", "replace").decode(), fill=(200, 0, 0, 255))
    return bg.convert("RGB")


def pts(pg, names):
    return pg.evaluate(f"VRM3D._pts({json.dumps(names)})")


def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def load(br, model: Path, site: Path):
    link = site / "model.vrm"
    if link.exists() or link.is_symlink():
        link.unlink()
    os.symlink(model, link)
    pg = br.new_page(viewport={"width": 1400, "height": 760})
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/app.html")
    pg.wait_for_function("window.VRM3D && VRM3D.ready", polling=500, timeout=300000)
    pg.evaluate("VRM3D._freeze(true); VRM3D.stage(true,1400,760,300,40); VRM3D.state('listen','calm','')")
    step(pg, 120)
    return pg


def sit_down(pg, sec=4.0):
    pg.evaluate("VRM3D.sit(true)")
    step(pg, int(sec * 60))


# ---------- замеры «как есть» ----------
STAND_POSES = ["rest", "clasp", "foldArms", "think", "behind", "hip"]


def hand_jitter(pg, dt):
    """Максимум второй разности положения кисти (мм) за 1 с после 2 с успокоения."""
    step(pg, int(2 / dt), dt)
    prev, worst = [], 0.0
    for _ in range(int(1 / dt)):
        step(pg, 1, dt)
        p = pts(pg, ["leftHand", "rightHand"])
        prev.append(p)
        if len(prev) >= 3:
            for h in ("leftHand", "rightHand"):
                a, b, c = prev[-3][h], prev[-2][h], prev[-1][h]
                worst = max(worst, 1000 * math.sqrt(sum((c[i] - 2 * b[i] + a[i]) ** 2 for i in range(3))))
    return worst


@check("jitter_now")
def _jitter_now(pg, name, shots):
    out = {}
    for pose in STAND_POSES:
        pg.evaluate(f"VRM3D.idle('{pose}', 9999)")
        out[pose] = {f"{round(1/dt)}fps": round(hand_jitter(pg, dt), 3) for dt in (1 / 20, 1 / 30, 1 / 60)}
    worst = max(v for d in out.values() for v in d.values())
    return True, f"худшая дрожь {worst:.2f} мм", out


def foot_contacts(pg, speed_goal=900, sec=6.0, dt=1 / 60):
    """Идёт вправо; для каждой опоры ступни — насколько она проехала по полу (см)."""
    pg.evaluate(f"VRM3D.walkTo({speed_goal})")
    step(pg, 60, dt)                                    # разгон
    tr = {"leftFoot": [], "rightFoot": []}
    for _ in range(int(sec / dt)):
        step(pg, 1, dt)
        p = pts(pg, ["leftFoot", "rightFoot"])
        for f in tr:
            tr[f].append(p[f])
    slides = []
    for f, xs in tr.items():
        ymin = min(p[1] for p in xs)
        run = []
        for p in xs + [[0, 1e9, 0]]:
            if p[1] < ymin + 0.012:
                run.append(p)
            elif run:
                if len(run) > 4:
                    slides.append(100 * max(dist([a[0], a[2]], [b[0], b[2]]) for a in run for b in run))
                run = []
    return slides


@check("foot_slide_now")
def _foot_slide_now(pg, name, shots):
    s = foot_contacts(pg)
    med = sorted(s)[len(s) // 2] if s else -1
    return True, f"опор {len(s)}, скольжение медиана {med:.1f} см, макс {max(s) if s else -1:.1f} см", s


@check("armhits_now")
def _armhits_now(pg, name, shots):
    out = {}
    for pose in STAND_POSES[1:]:
        pg.evaluate(f"VRM3D.idle('{pose}', 9999)")
        step(pg, 90)
        out[pose] = sum(pg.evaluate("(()=>{VRM3D._step(1,1/60);return VRM3D._armHits();})()") for _ in range(30))
    return True, f"точек в теле {sum(out.values())}", out


VIEWS = [(0, "front"), (-15, "below15"), (-30, "below30")]


def exposure(pg, shots, label):
    worst = 0.0
    for elev, vname in VIEWS:
        pg.evaluate(f"VRM3D._cam({elev}, 0, 2.6, 0.1)")
        e = pg.evaluate("VRM3D._exposed()")
        worst = max(worst, e)
        shots.append(shot(pg, f"{label} {vname}: {e:.2f}"))
    pg.evaluate("VRM3D._cam(null)")
    return worst


@check("skirt_now")
def _skirt_now(pg, name, shots):
    stand = exposure(pg, shots, f"{name} stand")
    sit_down(pg)
    sit = exposure(pg, shots, f"{name} sit")
    return True, f"видно стоя {stand:.2f}, сидя {sit:.2f}", {"stand": stand, "sit": sit}


# ---------- посадка (выпуск A) ----------
VIEWS_SIT = VIEWS + [(-15, "below15 left25", 25), (-15, "below15 right25", -25)]


def exposure_sit(pg, shots, label):
    worst = 0.0
    for v in VIEWS_SIT:
        elev, vname, azim = v[0], v[1], (v[2] if len(v) > 2 else 0)
        pg.evaluate(f"VRM3D._cam({elev}, {azim}, 2.6, 0.1)")
        e = pg.evaluate("VRM3D._exposed()")
        if elev >= 0:                                     # итог: спереди строго; снизу — в листе кадров для глаз
            worst = max(worst, e)
        shots.append(shot(pg, f"{label} {vname}: {e:.2f}"))
    pg.evaluate("VRM3D._cam(null)")
    return worst


@check("skirt_side_sit")
def _skirt_side_sit(pg, name, shots):
    worst, frames, seq = 0.0, [], []
    pg.evaluate("VRM3D.sit(true)")
    front_worst = 0.0
    for i in range(12):                                   # во время посадки тоже ничего не видно
        step(pg, 5 if i < 4 else 10)
        for el in (10, 0):                                # так её видно на самом деле (камера вровень/сверху) — строго 0
            pg.evaluate(f"VRM3D._cam({el}, 0, 2.6, 0.1)")
            front_worst = max(front_worst, pg.evaluate("VRM3D._exposed()"))
        pg.evaluate("VRM3D._cam(-15, 0, 2.6, 0.1)")
        e = pg.evaluate("VRM3D._exposed()")
        worst = max(worst, e)
        seq.append(round(e, 2))
        frames.append(shot(pg, f"{name} t={(i + 1) / 6:.1f}s {e:.2f}"))
        if e > 0 and os.environ.get("SAVEDIR"):
            frames[-1].save(Path(os.environ["SAVEDIR"]) / f"exp_{name.replace('/', '_')}_{i}.png")
        pg.evaluate("VRM3D._cam(null)")
    step(pg, 150)
    final = exposure_sit(pg, shots, f"{name} sit")
    shots.extend(frames if os.environ.get("ALLFRAMES") else frames[::3])
    worst = max(worst, final)
    hips = pts(pg, ["hips"])["hips"][1]
    # спереди и сверху — ничего; снизу 15° (запас) — не больше одной точки из 24 и итоговая поза — ничего спереди
    ok = front_worst <= 0.0 and worst <= 0.05 and hips >= 0.08
    return ok, f"спереди {front_worst:.2f}; снизу15 {worst:.2f}: посадка {seq}, итог {final:.2f}; таз {hips:.2f} м", {"front": front_worst, "exposed": worst, "seq": seq, "final": final, "hipsY": hips}


@check("skirt_old_sit")
def _skirt_old_sit(pg, name, shots):
    """Калибровка метрики: стоит — 0, старая поза «обняла колени» — должна ловиться."""
    stand = exposure_sit(pg, shots, f"{name} stand")
    pg.evaluate("VRM3D._oldSit(true)")
    sit_down(pg)
    old = exposure_sit(pg, shots, f"{name} old")
    return stand == 0, f"стоит {stand:.2f}, старая посадка {old:.2f}", {"stand": stand, "old": old}


@check("skirt_through_legs")
def _skirt_through_legs(pg, name, shots):
    sit_down(pg, 5)
    n = max(pg.evaluate("(()=>{VRM3D._step(1,1/60);return VRM3D._skirtInLegs();})()") for _ in range(60))
    return n == 0, f"точек подола в бёдрах: {n}", n


JUMP_BONES = ["hips", "spine", "chest", "head", "leftUpperLeg", "rightUpperLeg", "leftLowerLeg", "rightLowerLeg",
              "leftUpperArm", "rightUpperArm", "leftLowerArm", "rightLowerArm", "leftFoot", "rightFoot"]


def qang(a, b):
    d = abs(sum(x * y for x, y in zip(a, b)))
    return 2 * math.acos(min(1.0, d))


def watch_jumps(pg, sec, dt=1 / 60, every=1):
    """Рывок: насколько резко меняется скорость поворота кости от кадра к кадру (рад/кадр).
    Быстрое, но плавное движение (пружина) рывком не считается; телепорт кости — считается.
    Возвращает (худший рывок, самая низкая точка таза)."""
    worst, low, prev, vel = 0.0, 9.0, None, {}
    for _ in range(int(sec / dt / every)):
        step(pg, every, dt)
        r = pg.evaluate(f"VRM3D._rots({json.dumps(JUMP_BONES)})")
        low = min(low, pts(pg, ["hips"])["hips"][1])
        if prev:
            for n in r:
                if n not in prev:
                    continue
                v = qang(r[n], prev[n]) / every
                if n in vel:
                    worst = max(worst, abs(v - vel[n]))
                vel[n] = v
        prev = r
    return worst, low


@check("sit_to_lie")
def _sit_to_lie(pg, name, shots):
    pg.evaluate("VRM3D.sit(true)")
    j1, l1 = watch_jumps(pg, 4)
    shots.append(shot(pg, f"{name} sit"))
    pg.evaluate("VRM3D.lie(true)")
    j2, l2 = watch_jumps(pg, 8)
    shots.append(shot(pg, f"{name} lie"))
    pg.evaluate("VRM3D.lie(false); VRM3D.sit(false)")
    j3, l3 = watch_jumps(pg, 8)
    shots.append(shot(pg, f"{name} up"))
    p = pg.evaluate("VRM3D.pos()")
    worst, low = max(j1, j2, j3), l1
    # посадка (новый слой) — без рывков; «ложится/встаёт» — старый клип, допускаем его плавный вход (до 0,4 рад/кадр)
    ok = j1 < 0.12 and max(j2, j3) < 0.4 and low >= 0.08 and p["posture"] == "stand" and (p["sitK"] or 0) == 0 and (p["lieK"] or 0) < 0.01
    return ok, f"скачок {worst:.3f} рад (сесть {j1:.3f}, лечь {j2:.3f}, встать {j3:.3f}), таз не ниже {low:.2f} м, итог {p['posture']}", \
        {"jump": worst, "low": low}


def to_ledge(pg):
    """Прыгает на край окна (y=400 пикселей) и ждёт приземления."""
    pg.evaluate("VRM3D.ledges([[1, 150, 1000, 400]]); VRM3D.jumpTo(400, 400, 1)")
    step(pg, 150)
    return pg.evaluate("VRM3D.support()")


@check("skirt_edge_sit")
def _skirt_edge_sit(pg, name, shots):
    if to_ledge(pg) != 1:
        return False, "не запрыгнула на край", None
    pg.evaluate("VRM3D.sitEdge(true)")
    front, low15, seq = 0.0, 0.0, []
    for i in range(12):
        step(pg, 10)
        for el in (10, 0):
            pg.evaluate(f"VRM3D._cam({el}, 0, 2.6, 0.1)")
            front = max(front, pg.evaluate("VRM3D._exposed()"))
        pg.evaluate("VRM3D._cam(-15, 0, 2.6, 0.1)")
        e = pg.evaluate("VRM3D._exposed()"); low15 = max(low15, e); seq.append(round(e, 2))
        if i % 3 == 2:
            shots.append(shot(pg, f"{name} edge t={(i + 1) / 6:.1f}s {e:.2f}"))
        pg.evaluate("VRM3D._cam(null)")
    step(pg, 240)                                         # сидит и болтает ногами
    for el in (10, 0, -15):
        pg.evaluate(f"VRM3D._cam({el}, 0, 2.6, 0.1)")
        e = pg.evaluate("VRM3D._exposed()")
        if el >= 0: front = max(front, e)
        else: low15 = max(low15, e)
        shots.append(shot(pg, f"{name} edge {el}: {e:.2f}"))
    pg.evaluate("VRM3D._cam(null)")
    shots.append(shot(pg, f"{name} edge normal"))
    p = pg.evaluate("VRM3D.pos()")
    ok = front <= 0 and low15 <= 0.05 and p["edgeK"] and p["edgeK"] > 0.99
    return ok, f"спереди {front:.2f}; снизу15 {low15:.2f} {seq}; edgeK {p['edgeK']}", {"front": front, "low15": low15}


@check("skirt_crouch")
def _skirt_crouch(pg, name, shots):
    front, low15 = 0.0, 0.0
    pg.evaluate("VRM3D.ledges([[1, 150, 1000, 400]]); VRM3D.jumpTo(400, 400, 1)")
    for i in range(18):                                  # присед, полёт, приземление
        step(pg, 5)
        for el in (10, 0, -15):
            pg.evaluate(f"VRM3D._cam({el}, 0, 2.6, 0.1)")
            e = pg.evaluate("VRM3D._exposed()")
            if el >= 0: front = max(front, e)
            else: low15 = max(low15, e)
        if i in (3, 6, 15):
            shots.append(shot(pg, f"{name} jump {i}: {e:.2f}"))
        pg.evaluate("VRM3D._cam(null)")
    return front <= 0 and low15 <= 0.05, f"спереди {front:.2f}; снизу15 {low15:.2f}", {"front": front, "low15": low15}


@check("edge_fall_midsit")
def _edge_fall_midsit(pg, name, shots):
    if to_ledge(pg) != 1:
        return False, "не запрыгнула на край", None
    pg.evaluate("VRM3D.sitEdge(true)")
    step(pg, 60)                                         # посреди посадки окно закрыли
    pg.evaluate("VRM3D.ledges([])")
    j, low = watch_jumps(pg, 3)
    p = pg.evaluate("VRM3D.pos()")
    shots.append(shot(pg, f"{name} fell"))
    ok = p["support"] is None and not p["jump"] and p["posture"] == "stand" and j < 0.25   # гаснет за 0,25 с — плавно
    return ok, f"скачок {j:.3f} рад, опора {p['support']}, поза {p['posture']}", {"jump": j}


# ---------- запуск ----------
def sheet(images, cols=6):
    if not images:
        return None
    w, h = 300, 300
    rows = math.ceil(len(images) / cols)
    out = Image.new("RGB", (cols * w, rows * h), (255, 255, 255))
    for i, im in enumerate(images):
        im = im.copy()
        im.thumbnail((w, h))
        out.paste(im, ((i % cols) * w, (i // cols) * h))
    return out


def main():
    site, out = Path(sys.argv[1]), Path(sys.argv[2])
    names = sys.argv[3:] or list(CHECKS)
    out.mkdir(parents=True, exist_ok=True)
    only = [m for m in os.environ.get("MODELS", "").split(",") if m]
    models = [m for m in sorted(AV.glob("*/*.vrm")) if not only or f"{m.parent.name}/{m.stem}" in only]
    results, failed, shots = {}, 0, {n: [] for n in names}
    with sync_playwright() as p:
        br = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist",
                                     "--enable-unsafe-swiftshader"])
        for m in models:
            mname = f"{m.parent.name}/{m.stem}"
            for n in names:
                try:
                    pg = load(br, m, site)
                    ok, msg, val = CHECKS[n](pg, mname, shots[n])
                    if pg.errors:
                        ok, msg = False, msg + " | ОШИБКИ: " + "; ".join(pg.errors[:2])
                    pg.close()
                except Exception as e:                       # проверка упала — это FAIL, а не тишина
                    ok, msg, val = False, f"упала: {e}", None
                results.setdefault(n, {})[mname] = {"ok": ok, "msg": msg, "value": val}
                failed += not ok
                print(f"{'PASS' if ok else 'FAIL'}  {n:22s} {mname:16s} {msg}", flush=True)
    for n, ims in shots.items():
        s = sheet(ims)
        if s:
            s.save(out / f"{n}.png")
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nИтого: {'всё прошло' if not failed else f'не прошло {failed}'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
