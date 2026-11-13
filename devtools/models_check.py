"""Каждая модель: загрузка, физика, руки в позах и на ходу, кадр стоя и на ходу."""
import base64
import io
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

SITE, OUT = Path(sys.argv[1]), Path(sys.argv[2])
AV = Path.home() / "Podruga" / "avatars"
models = sorted(AV.glob("*/*.vrm"))
tiles = []
with sync_playwright() as p:
    br = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader"])
    for m in models:
        link = SITE / "model.vrm"
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink(m, link)
        pg = br.new_page(viewport={"width": 1400, "height": 760})
        logs = []
        pg.on("console", lambda msg: logs.append(msg.text) if "[3D]" in msg.text else None)
        pg.on("pageerror", lambda e: logs.append("ОШИБКА " + str(e)))
        pg.goto("http://127.0.0.1:8766/app.html")
        try:
            pg.wait_for_function("window.VRM3D && VRM3D.ready", timeout=180000)
        except Exception:
            print(f"{m.parent.name}/{m.stem}: НЕ ЗАГРУЗИЛАСЬ", logs[-3:], flush=True)
            pg.close()
            continue
        pg.evaluate("VRM3D._freeze(true); VRM3D.stage(true,1400,760,300,40); VRM3D.state('listen','calm','')")
        pg.evaluate("VRM3D._step(90,1/60)")
        hits = 0
        for pose in ["clasp", "foldArms", "think", "behind", "hip"]:
            pg.evaluate(f"VRM3D.idle('{pose}', 999); VRM3D._step(90,1/60)")
            hits += pg.evaluate("(()=>{let n=0;for(let i=0;i<60;i++){VRM3D._step(1,1/60);n+=VRM3D._armHits();}return n;})()")
        pg.evaluate("VRM3D.idle('rest', 999); VRM3D._step(90,1/60)")
        stand = pg.evaluate("(VRM3D._step(0), document.getElementById('vrmCanvas').toDataURL('image/png').split(',')[1])")
        pg.evaluate("VRM3D.walkTo(1200); VRM3D._step(140,1/60)")
        whits = pg.evaluate("(()=>{let n=0;for(let i=0;i<120;i++){VRM3D._step(1,1/60);n+=VRM3D._armHits();}return n;})()")
        walk = pg.evaluate("(VRM3D._step(0), document.getElementById('vrmCanvas').toDataURL('image/png').split(',')[1])")
        phys = next((l for l in logs if "физика" in l), "")
        size = next((l for l in logs if "размеры окна" in l), "")
        print(f"{m.parent.name}/{m.stem}: руки в позах {hits} точек/300 кадров, на ходу {whits}/120 | {phys[5:]} | {size[5:]}", flush=True)
        tiles.append((f"{m.parent.name}/{m.stem}", stand, walk))
        pg.close()
    br.close()
ims = []
for lab, s, w in tiles:
    a = Image.open(io.BytesIO(base64.b64decode(s))).convert("RGBA")
    b = Image.open(io.BytesIO(base64.b64decode(w))).convert("RGBA")
    h = 530
    c = Image.new("RGBA", (a.width + b.width, h), (120, 130, 150, 255))
    c.paste(a, (0, h - a.height), a)
    c.paste(b, (a.width, h - b.height), b)
    ImageDraw.Draw(c).text((6, 6), lab, fill=(255, 255, 255, 255))
    ims.append(c.resize((c.width // 2, c.height // 2)))
cols = 5
w = max(i.width for i in ims)
h = max(i.height for i in ims)
sheet = Image.new("RGB", (cols * w, ((len(ims) + cols - 1) // cols) * h), (120, 130, 150))
for k, i in enumerate(ims):
    sheet.paste(i, ((k % cols) * w, (k // cols) * h), i)
sheet.save(OUT / "all_models.png")
print("лист готов", flush=True)
