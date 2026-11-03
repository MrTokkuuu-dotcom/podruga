"""Отдельный процесс с голосом Chatterbox (запускается в своём venv_cb — у него свои версии
библиотек, несовместимые с основной программой). Протокол: по строке JSON на вход и выход."""
import base64
import json
import os
import sys
import time

# всё, что печатают библиотеки, уходит в stderr; ответы — только в настоящий stdout
proto = os.fdopen(os.dup(1), "w", buffering=1)
os.dup2(2, 1)
sys.stdout = sys.stderr


def send(obj):
    proto.write(json.dumps(obj) + "\n")
    proto.flush()


def main():
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    model, dev = None, None
    for d in (["mps"] if torch.backends.mps.is_available() else []) + ["cpu"]:
        try:
            model = ChatterboxMultilingualTTS.from_pretrained(device=d)
            dev = d
            break
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[chatterbox] {d}: {e}", file=sys.stderr)
    if model is None:
        send({"error": "модель не загрузилась"})
        return
    send({"ready": True, "device": dev, "sr": model.sr})
    for line in sys.stdin:
        try:
            req = json.loads(line)
            t0 = time.time()
            wav = model.generate(req["text"], language_id=req.get("lang", "ru"),
                                 audio_prompt_path=req.get("prompt") or None,
                                 exaggeration=req.get("exaggeration", 0.5),
                                 cfg_weight=req.get("cfg", 0.5))
            a = (wav.squeeze().detach().cpu().numpy() * 32767).clip(-32768, 32767).astype("int16")
            send({"pcm": base64.b64encode(a.tobytes()).decode(), "sr": model.sr,
                  "secs": round(time.time() - t0, 2)})
        except Exception as e:
            send({"error": str(e)[:300]})


if __name__ == "__main__":
    main()
