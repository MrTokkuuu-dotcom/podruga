"""Кастомизация: какая девочка и в каком наряде. Модели лежат в ~/Podruga/avatars/<девочка>/<наряд>.vrm,
список — в avatars.json рядом с программой. Нет файла — скачивается из ветки avatars на GitHub
(в основной код модели не кладём: обновление качало бы сотни мегабайт)."""
import json
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = "https://raw.githubusercontent.com/{repo}/avatars/{girl}/{outfit}.vrm"


class Avatars:
    def __init__(self, home: Path):
        self.home = Path(home)
        self.dir = self.home / "avatars"
        try:
            self.data = json.loads((ROOT / "avatars.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            self.data = {"girls": []}
        self._migrate()

    def _migrate(self):
        """Нынешняя Аня (~/Podruga/avatar.vrm) — это «Аня, пальто и корсет»."""
        dst = self.dir / "anya" / "default.vrm"
        src = self.home / "avatar.vrm"
        if not dst.exists() and src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def path(self, girl: str, outfit: str) -> Path:
        return self.dir / girl / f"{outfit}.vrm"

    def girl(self, gid: str) -> dict | None:
        return next((g for g in self.data["girls"] if g["id"] == gid), None)

    def listing(self, current: str) -> dict:
        """Для окна настроек: девочки, наряды, есть ли файл, что выбрано сейчас."""
        girls = []
        for g in self.data["girls"]:
            girls.append({"id": g["id"], "name": g["name"], "about": g.get("about", ""),
                          "outfits": [{"id": o["id"], "name": o["name"], "have": self.path(g["id"], o["id"]).exists()}
                                      for o in g["outfits"]]})
        return {"girls": girls, "current": current or "anya/default"}

    def ensure(self, girl: str, outfit: str, repo: str) -> Path | None:
        p = self.path(girl, outfit)
        if p.exists():
            return p
        url = RAW.format(repo=repo, girl=girl, outfit=outfit)
        tmp = p.with_suffix(".part")
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
            if tmp.stat().st_size < 1_000_000:
                raise RuntimeError("файл слишком маленький — похоже, его ещё нет")
            tmp.replace(p)
            return p
        except Exception as e:
            print(f"[образы] не скачалось {girl}/{outfit}: {e}")
            tmp.unlink(missing_ok=True)
            return None

    def activate(self, girl: str, outfit: str) -> bool:
        """Сделать модель текущей: её берёт окно при загрузке (~/Podruga/avatar.vrm)."""
        p = self.path(girl, outfit)
        if not p.exists():
            return False
        shutil.copy2(p, self.home / "avatar.vrm")
        return True
