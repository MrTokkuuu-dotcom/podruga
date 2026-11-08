"""Самообновление библиотек. Если после обновления изменился requirements.txt,
при запуске она сама доставит нужное (через свой uv) и перезапустится.
Только стандартная библиотека — запускается раньше всего остального."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path(os.environ.get("PODRUGA_HOME", ROOT))


def _notify(text: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["osascript", "-e", f'display notification "{text}" with title "Подруга"'],
                       capture_output=True)


def ensure_deps() -> None:
    req = ROOT / "requirements.txt"
    uv = HOME / "bin" / "uv"
    if os.environ.get("PODRUGA_BUNDLED"):
        return                      # подписанное приложение: библиотеки внутри него, менять их нельзя
    if not req.exists() or not uv.exists():
        return                      # запуск из папки разработки — ничего не делаем
    stamp = HOME / ".deps_stamp"
    digest = hashlib.sha1(req.read_bytes()).hexdigest()
    if stamp.exists() and stamp.read_text().strip() == digest:
        return
    print("[обновление] ставлю новые библиотеки…", flush=True)
    _notify("Обновляюсь — минутку…")
    r = subprocess.run([str(uv), "pip", "install", "--python", sys.executable, "-q", "-r", str(req)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[обновление] не получилось:\n{r.stderr[-2000:]}", flush=True)
        _notify("Обновление не встало — работаю как раньше")
        return
    stamp.write_text(digest)
    print("[обновление] готово, перезапускаюсь", flush=True)
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ---------- обновление кода с GitHub ----------
# В update.json лежит {"repo": "владелец/репозиторий", "branch": "main"}. В репозитории — файл VERSION
# (число). Если там число больше нашего — скачиваем архив, кладём новый код поверх и перезапускаемся.
# Личное (ключ, память, настройки, модель голоса) лежит в ~/Podruga, а не в папке кода, — его не трогаем.
KEEP = {"__pycache__", "voices", "models"}       # тяжёлое и скачанное на месте


def _local_version() -> int:
    try:
        return int((ROOT / "VERSION").read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0


def _ssl_context():
    """У «своего» Python от uv может не быть списка сертификатов — берём certifi или системный."""
    import ssl
    for path in (_certifi(), "/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"):
        if path and os.path.exists(path):
            try:
                return ssl.create_default_context(cafile=path)
            except Exception:
                pass
    return ssl.create_default_context()


def _certifi():
    try:
        import certifi
        return certifi.where()
    except Exception:
        return None


def check_update() -> None:
    cfg_file = ROOT / "update.json"
    if not cfg_file.exists() or os.environ.get("PODRUGA_NO_UPDATE") or not (
            (HOME / "bin" / "uv").exists() or os.environ.get("PODRUGA_BUNDLED")):
        return
    import json
    import shutil
    import tempfile
    import urllib.request
    import zipfile
    try:
        cfg = json.loads(cfg_file.read_text())
        repo, branch = cfg["repo"], cfg.get("branch", "main")
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/VERSION"
        ctx = _ssl_context()
        req = urllib.request.Request(url + f"?t={int(__import__('time').time())}",   # мимо кэша GitHub
                                     headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
            remote = int(r.read().decode().strip())
    except Exception as e:
        print(f"[обновление] не проверилось: {e}", flush=True)
        return
    local = _local_version()
    print(f"[обновление] у меня версия {local}, на GitHub {remote}", flush=True)
    if remote <= local:
        return
    print(f"[обновление] есть новая версия {remote} (у меня {local}), скачиваю…", flush=True)
    _notify("Нашла обновление — ставлю, это минутка")
    try:
        tmp = Path(tempfile.mkdtemp(prefix="podruga_upd_"))
        zpath = tmp / "code.zip"
        zurl = f"https://codeload.github.com/{repo}/zip/refs/heads/{branch}"
        with urllib.request.urlopen(zurl, timeout=180, context=ctx) as r, open(zpath, "wb") as f:
            shutil.copyfileobj(r, f)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(tmp / "x")
        src = next(p for p in (tmp / "x").iterdir() if p.is_dir())
        if not (src / "main.py").exists() or not (src / "VERSION").exists():
            raise RuntimeError("в архиве нет main.py — это не тот репозиторий")
        backup = HOME / "app_previous"                       # прошлая версия — на всякий случай
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        shutil.copytree(ROOT, backup, ignore=shutil.ignore_patterns(*KEEP))
        for item in src.iterdir():
            dst = ROOT / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        print(f"[обновление] не получилось: {e}", flush=True)
        _notify("Обновление не встало — работаю как раньше")
        return
    (HOME / "updated_to.txt").write_text(str(remote))
    print(f"[обновление] обновилась до версии {remote}, перезапускаюсь", flush=True)
    os.execv(sys.executable, [sys.executable] + sys.argv)
