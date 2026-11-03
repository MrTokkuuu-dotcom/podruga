"""Журнал: в приложении всё, что печатается, уходит в log.txt со временем.
Плюс ошибки в фоновых потоках больше не пропадают молча."""
import sys
import threading
import traceback
from datetime import datetime


class _Stamped:
    def __init__(self, stream):
        self.stream = stream
        self.fresh = True

    def write(self, text):
        out = []
        for part in text.splitlines(keepends=True):
            if self.fresh and part.strip():
                out.append(datetime.now().strftime("%H:%M:%S ") + part)
            else:
                out.append(part)
            self.fresh = part.endswith("\n")
        self.stream.write("".join(out))
        self.stream.flush()

    def flush(self):
        self.stream.flush()


def setup() -> None:
    if not sys.stdout.isatty():
        sys.stdout = _Stamped(sys.stdout)
        sys.stderr = _Stamped(sys.stderr)

    def hook(args):
        print(f"[ошибка в потоке {args.thread.name if args.thread else '?'}]")
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    threading.excepthook = hook
