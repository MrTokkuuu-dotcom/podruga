"""Привычки (habits.py): замечает, что он делает в одно время, предлагает, слушается «нет».
Запуск: ~/Podruga/venv/bin/python devtools/test_habits.py"""
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import habits  # noqa: E402

bad = []


def check(name, got, want):
    if got != want:
        bad.append(f"{name}: {got!r} != {want!r}")


now = [datetime(2026, 11, 28, 21, 0).timestamp()]
H = habits.Habits(Path(tempfile.mkdtemp()) / "habits.json", clock=lambda: now[0])
base = datetime(2026, 11, 28, 21, 0)

check("похоже на привычку", H.is_habit_like("включи лоу-фай в ютуб музыке"), True)
check("пауза — нет", H.is_habit_like("поставь на паузу"), False)
check("громкость — нет", H.is_habit_like("включи погромче"), False)
check("разговор — нет", H.is_habit_like("как дела"), False)


def did(phrase, days_ago, hh, mm):
    now[0] = (base - timedelta(days=days_ago)).replace(hour=hh, minute=mm).timestamp()
    H.note(phrase)


did("включи лоу-фай в ютуб музыке", 1, 21, 5)
did("включи лоу фай в ютуб музыке", 2, 20, 50)
check("два дня — рано", H.suggestion(base), None)
did("включи лоу-фай в ютуб музыке", 4, 21, 20)
did("открой почту", 1, 9, 0)
did("открой почту", 2, 9, 10)
did("открой почту", 3, 9, 5)
s = H.suggestion(base)
check("три дня — предлагает", (s[1], s[2]) if s else None, ("включи лоу-фай в ютуб музыке", 3))
check("утром не вечернее", H.suggestion(base.replace(hour=8, minute=55))[1], "открой почту")
check("днём ничего", H.suggestion(base.replace(hour=15)), None)
check("заранее за 30 мин", H.suggestion(base.replace(hour=20, minute=40)) is not None, True)
H.mark_offered(s[0], base)
check("раз в день", H.suggestion(base.replace(minute=10)), None)
check("завтра снова", H.suggestion(base + timedelta(days=1)) is not None, True)
H.answer(s[0], False)
H.answer(s[0], False)
check("два нет — молчит", H.suggestion(base + timedelta(days=2)), None)
check("через 2 недели снова", H.suggestion(base + timedelta(days=15)) is not None, True)
# сегодня уже делал — не напоминать
did("открой почту", 0, 8, 30)
check("сегодня уже было", H.suggestion(base.replace(hour=9)), None)
# режим — всегда
check("режим", H.note("рабочий режим", mode=True), True)
check("никогда", habits.never("нет, больше не предлагай"), True)
check("описание", any("почту" in x for x in H.describe(base)), True)
check("забыть", H.forget_all() > 0 and H.suggestion(base) is None, True)

print("\n".join(bad) if bad else "OK")
sys.exit(1 if bad else 0)
