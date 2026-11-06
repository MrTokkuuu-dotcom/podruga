"""Настройки. Где что лежит:
- код и config.yaml (настройки по умолчанию) — в папке программы (ROOT);
- личное (ключ .env, память, журнал, settings.json с твоими изменениями) — в HOME.
  В установленном приложении HOME = ~/Library/Application Support/Podruga,
  при запуске из папки — сама папка программы (как раньше)."""
import json
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
HOME = Path(os.environ.get("PODRUGA_HOME", ROOT))

USER_KEYS = {"companion_name", "user_name", "voice", "style", "pitch",
             "trait_bold", "trait_play", "trait_talk", "walk", "guests"}   # что меняется из окна настроек
TRAITS_DEFAULT = {"trait_bold": "20", "trait_play": "55", "trait_talk": "30"}
SILERO_SPEAKERS = {"xenia", "kseniya", "baya"}


def env_path() -> Path:
    return HOME / ".env"


def _load_env_file() -> None:
    env = env_path()
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not os.environ.get(key.strip()):
            os.environ[key.strip()] = value.strip().strip('"')


def set_env(name: str, value: str | None) -> None:
    """Записать (или убрать) одну переменную в ~/Podruga/.env, не трогая остальные."""
    HOME.mkdir(parents=True, exist_ok=True)
    lines = []
    if env_path().exists():
        lines = [l for l in env_path().read_text(encoding="utf-8").splitlines()
                 if l.partition("=")[0].strip() != name]
    if value:
        lines.append(f"{name}={value}")
        os.environ[name] = value
    else:
        os.environ.pop(name, None)
    env_path().write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(env_path(), 0o600)
    except OSError:
        pass


def save_key(key: str) -> None:
    set_env("GEMINI_API_KEY", key)


def has_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def settings_path(cfg: dict) -> Path:
    return cfg["_data_dir"] / "settings.json"


def apply_user_settings(cfg: dict) -> None:
    try:
        s = json.loads(settings_path(cfg).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return
    if s.get("companion_name"):
        cfg["companion_name"] = s["companion_name"]
    if s.get("user_name"):
        cfg["user_name"] = s["user_name"]
    if s.get("voice"):
        if s["voice"] == "chatterbox":
            cfg["voice"]["engine"] = "chatterbox"
        elif s["voice"] in SILERO_SPEAKERS:
            cfg["voice"]["engine"] = "silero"
            cfg["voice"]["silero_speaker"] = s["voice"]
        else:
            cfg["voice"]["engine"] = "gemini"
            cfg["voice"]["gemini_voice"] = s["voice"]
    if s.get("pitch"):
        cfg["voice"]["silero_pitch"] = s["pitch"]
    if s.get("style"):
        cfg["voice"]["style"] = s["style"]
    cfg["traits"] = {k: int(s.get(k, v)) for k, v in TRAITS_DEFAULT.items()}
    if s.get("walk") in ("0", "1"):
        cfg.setdefault("walk", {})["enabled"] = s["walk"] == "1"


def save_user_settings(cfg: dict, values: dict) -> None:
    clean = {k: str(v) for k, v in values.items()
             if k in USER_KEYS and isinstance(v, (str, int)) and str(v).strip()}
    path = settings_path(cfg)
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        old = {}
    old.update(clean)
    path.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
    apply_user_settings(cfg)


def load_config(path: Path = ROOT / "config.yaml") -> dict:
    _load_env_file()
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    data_dir = HOME / cfg["paths"]["data_dir"]
    data_dir.mkdir(parents=True, exist_ok=True)
    cfg["_data_dir"] = data_dir
    cfg["traits"] = {k: int(v) for k, v in TRAITS_DEFAULT.items()}
    apply_user_settings(cfg)
    return cfg
