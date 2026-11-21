"""Кастомизация: какая девочка и в каком наряде. Модели лежат в ~/Podruga/avatars/<девочка>/<наряд>.vrm,
список — в avatars.json рядом с программой. Нет файла — скачивается из ветки avatars на GitHub
(в основной код модели не кладём: обновление качало бы сотни мегабайт)."""
import json
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = "https://raw.githubusercontent.com/{repo}/avatars/{girl}/{outfit}.vrm"


def persona(gid: str) -> dict:
    """Характер девочки из avatars.json: traits (ползунки по умолчанию), character (для Google),
    motion (как двигается: любимые позы, скорость, покачивание)."""
    try:
        data = json.loads((ROOT / "avatars.json").read_text(encoding="utf-8"))
        g = next((g for g in data["girls"] if g["id"] == gid), None)
        return (g or {}).get("persona", {})
    except (FileNotFoundError, ValueError):
        return {}


def current_girl(cfg: dict) -> str:
    return (cfg.get("avatar_choice") or "anya/default").split("/")[0]


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
                          "outfits": [{"id": o["id"], "name": o["name"], "group": o.get("group", ""),
                                       "have": self.path(g["id"], o["id"]).exists()}
                                      for o in g["outfits"]]})
        return {"girls": girls, "current": current or "anya/default"}

    # --- номер правки модели: в avatars.json rev больше, чем скачано, — качаем заново ---
    def _revs_path(self) -> Path:
        return self.dir / "revs.json"

    def _revs(self) -> dict:
        try:
            return json.loads(self._revs_path().read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}

    def want_rev(self, girl: str, outfit: str) -> int:
        g = self.girl(girl) or {}
        o = next((o for o in g.get("outfits", []) if o["id"] == outfit), {})
        return int(o.get("rev", 1))

    def outdated(self, girl: str, outfit: str) -> bool:
        return self.path(girl, outfit).exists() and self._revs().get(f"{girl}/{outfit}", 1) < self.want_rev(girl, outfit)

    def ensure(self, girl: str, outfit: str, repo: str) -> Path | None:
        p = self.path(girl, outfit)
        if p.exists() and not self.outdated(girl, outfit):
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
            revs = self._revs()
            revs[f"{girl}/{outfit}"] = self.want_rev(girl, outfit)
            self._revs_path().write_text(json.dumps(revs, ensure_ascii=False, indent=1), encoding="utf-8")
            return p
        except Exception as e:
            print(f"[образы] не скачалось {girl}/{outfit}: {e}")
            tmp.unlink(missing_ok=True)
            return p if p.exists() else None              # обновить не вышло — остаётся прежняя

    def refresh(self, current: str, repo: str) -> bool:
        """Фоном при запуске: докачать обновлённые модели. True — текущая модель обновилась."""
        cur_changed = False
        for g in self.data["girls"]:
            for o in g["outfits"]:
                if self.outdated(g["id"], o["id"]):
                    print(f"[образы] есть новая версия {g['id']}/{o['id']} — скачиваю")
                    old = self._revs().get(f"{g['id']}/{o['id']}", 1)
                    self.ensure(g["id"], o["id"], repo)
                    if self._revs().get(f"{g['id']}/{o['id']}", 1) > old and f"{g['id']}/{o['id']}" == current:
                        cur_changed = self.activate(g["id"], o["id"])
        return cur_changed

    def activate(self, girl: str, outfit: str) -> bool:
        """Сделать модель текущей: её берёт окно при загрузке (~/Podruga/avatar.vrm)."""
        p = self.path(girl, outfit)
        if not p.exists():
            return False
        shutil.copy2(p, self.home / "avatar.vrm")
        return True
