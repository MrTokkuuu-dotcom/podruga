"""У каждой девочки свой голос, облачных голосов нет. Запуск: ~/Podruga/venv/bin/python devtools/test_voice_settings.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

d = Path(tempfile.mkdtemp())
config.settings_path = lambda c: d / "settings.json"
config._qwen_possible = lambda: True


def voice_for(settings: dict) -> tuple[str, str | None]:
    (d / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    cfg = {"voice": {"engine": "qwen"}, "brain": {}, "companion_name": "Аня", "user_name": "Дима"}
    config.apply_user_settings(cfg)
    return cfg["voice"]["engine"], cfg["voice"].get("qwen_voice")


assert voice_for({"avatar": "tanya/formal", "voice": "Sulafat"}) == ("qwen", "tanya"), "облачный голос не включается"
assert voice_for({"avatar": "alisa/street", "voice": "kseniya"}) == ("qwen", "alisa")
assert voice_for({"avatar": "anya/default", "voice": "tanya"}) == ("qwen", "anya"), "голос — девочки, а не из старых настроек"
assert voice_for({}) == ("qwen", "anya")
assert "voice" not in config.USER_KEYS and "style" not in config.USER_KEYS and "pitch" not in config.USER_KEYS

repo = Path(config.__file__).resolve().parent
for f in ("tts.py", "main.py", "ui.py", "config.yaml", "avatar/app_template.html"):
    txt = (repo / f).read_text(encoding="utf-8")
    assert "gemini_voice" not in txt and "GeminiVoiceOut" not in txt and "sVoice" not in txt, f
assert not (repo / "voice_gemini.py").exists()
print("OK")
