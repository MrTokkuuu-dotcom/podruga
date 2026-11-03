"""Примерочная голосов: одна и та же фраза разными голосами Gemini.
Понравившийся впиши в config.yaml → voice → gemini_voice."""
import subprocess
import sys
import wave

from config import ROOT, load_config

VOICES = [
    ("Leda", "юный"),
    ("Aoede", "лёгкий, воздушный"),
    ("Zephyr", "яркий"),
    ("Laomedeia", "бодрый"),
    ("Achernar", "мягкий"),
    ("Vindemiatrix", "нежный"),
    ("Sulafat", "тёплый"),
    ("Autonoe", "звонкий"),
]
PHRASE = "Привет! Я так рада тебя слышать. Как прошёл твой день? Расскажешь мне?"


def main():
    cfg = load_config()
    from voice_gemini import GeminiVoiceOut
    out_dir = ROOT / "voices" / "samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    v = cfg["voice"]
    for name, desc in VOICES:
        print(f"\n▶ {name} — {desc}")
        try:
            voice = GeminiVoiceOut(v["gemini_model"], name, v.get("style", ""))
            audio, rate = voice._request(PHRASE)
        except Exception as e:
            print(f"   не получилось: {str(e)[:200]}")
            continue
        path = out_dir / f"{name}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(audio.tobytes())
        if sys.platform == "darwin":
            subprocess.run(["afplay", str(path)])
    print(f"\nВсе образцы лежат в {out_dir} — можно переслушать.")
    print("Понравившееся имя впиши в config.yaml → gemini_voice.")


if __name__ == "__main__":
    main()
