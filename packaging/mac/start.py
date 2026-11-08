"""Первый шаг подписанного приложения: подготовить ~/Podruga (код, распознаватель команд) и запустить main.py.
Код и модели лежат снаружи приложения и обновляются с GitHub как раньше — само приложение
(подписанное) при этом не меняется, иначе подпись сломалась бы."""
import os
import shutil
import sys
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

CONTENTS = Path(__file__).resolve().parent.parent
SEED = CONTENTS / "Resources" / "app-seed"          # код на момент сборки — на случай первого запуска
HOME = Path(os.environ.get("PODRUGA_HOME", Path.home() / "Podruga"))
APP = HOME / "app"
VOSK = "vosk-model-small-ru-0.22"
KEEP = {"voices", "models", "__pycache__"}


def log_to_file():
    HOME.mkdir(parents=True, exist_ok=True)
    log = HOME / "log.txt"
    if log.exists() and log.stat().st_size > 5_000_000:
        log.replace(HOME / "log.txt.old")
    f = open(log, "a", buffering=1, encoding="utf-8")
    f.write(f"======== запуск (приложение) {datetime.now():%Y-%m-%d %H:%M:%S} ========\n")
    os.dup2(f.fileno(), 1)
    os.dup2(f.fileno(), 2)


def version(p: Path) -> int:
    try:
        return int((p / "VERSION").read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0


def seed_code():
    """Кода нет или он старше того, что внутри приложения, — кладём свой (скачанное оставляем)."""
    if version(APP) >= version(SEED):
        return
    print(f"[приложение] кладу код версии {version(SEED)} (было {version(APP)})", flush=True)
    APP.mkdir(parents=True, exist_ok=True)
    for item in SEED.iterdir():
        if item.name in KEEP:
            continue
        dst = APP / item.name
        if item.is_dir():
            shutil.copytree(item, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst)


def ensure_vosk():
    """Распознаватель «привет, подруга» (~45 МБ) — один раз."""
    d = APP / "voices" / VOSK
    if d.exists():
        return
    try:
        print("[приложение] скачиваю распознаватель команд…", flush=True)
        (APP / "voices").mkdir(parents=True, exist_ok=True)
        z = APP / "voices" / "vosk-ru.zip"
        urllib.request.urlretrieve(f"https://alphacephei.com/vosk/models/{VOSK}.zip", z)
        with zipfile.ZipFile(z) as f:
            f.extractall(APP / "voices")
        z.unlink()
    except Exception as e:
        print(f"[приложение] распознаватель команд не скачался ({e}) — будет слушать всё подряд", flush=True)


def main():
    log_to_file()
    os.environ["PODRUGA_HOME"] = str(HOME)
    os.environ["PODRUGA_APP"] = str(CONTENTS.parent)
    seed_code()
    ensure_vosk()
    os.chdir(APP)
    # -E -s: без чужих настроек Python и без пользовательских библиотек, но папка программы видна
    # ускоренные копии модулей (.pyc) — снаружи приложения: запись внутрь сломала бы подпись
    os.execv(sys.executable, [sys.executable, "-E", "-s", "-X", f"pycache_prefix={HOME / '.pycache'}",
                              str(APP / "main.py")])


if __name__ == "__main__":
    main()
