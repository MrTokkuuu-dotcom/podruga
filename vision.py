"""Зрение: скриншот экрана — только когда попросили («посмотри», «глянь», кнопка в окне).
На Mac — встроенная команда screencapture (первый раз macOS спросит разрешение
«Запись экрана»). Картинка уменьшается до 1600 px, чтобы было быстро и дёшево."""
import os
import subprocess
import sys
import tempfile

MAX_SIDE = 1600


def capture() -> bytes | None:
    """JPEG главного экрана или None, если не получилось."""
    try:
        if sys.platform == "darwin":
            return _capture_mac()
        return _capture_pil()
    except Exception as e:
        print(f"[зрение] не получилось сделать скриншот: {e}")
        return None


def _capture_mac() -> bytes | None:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    try:
        # -x без звука затвора, -m только главный экран, -t формат
        subprocess.run(["screencapture", "-x", "-m", "-t", "jpg", path],
                       check=True, timeout=10)
        subprocess.run(["sips", "-Z", str(MAX_SIDE), path],
                       check=False, timeout=10, capture_output=True)
        with open(path, "rb") as f:
            data = f.read()
        return data or None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _capture_pil() -> bytes | None:
    import io

    from PIL import ImageGrab
    img = ImageGrab.grab()
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=80)
    return buf.getvalue()
