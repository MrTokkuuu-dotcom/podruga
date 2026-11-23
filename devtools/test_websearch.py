"""Поиск без Google — только источники, которые можно использовать в продаже (нужен интернет).
Запуск: ~/Podruga/venv/bin/python devtools/test_websearch.py"""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import websearch  # noqa: E402

# города — из своего списка (GeoNames), с падежами
for word, want in {"Пусане": "пусан", "Сеуле": "сеул", "Москве": "москва", "부산": "부산", "Busan": "busan",
                   "Какая": None, "погода": None}.items():
    got = websearch.weather_city(word)
    assert (got and got[0]) == want, (word, got, want)

# погода — MET Norway, с цифрами
w = websearch.weather_text("Пусан")
assert "°" in w and "Пусан" in w and "MET Norway" in w, w
print(w)
assert websearch.is_weather("какая завтра погода в Пусане") and not websearch.is_weather("курс доллара")
assert websearch.needs_google("курс доллара к воне") and websearch.needs_google("последние новости")
assert not websearch.needs_google("кто такой Эйнштейн")

# справка — Википедия
res = websearch.wiki_search("Пусан")
assert res and any("Корея" in r["body"] or "Корей" in r["body"] for r in res), res
print(res[0]["title"], "—", res[0]["body"][:80])

# нет сети — ConnectionError
import requests  # noqa: E402
with mock.patch.object(requests, "get", side_effect=requests.ConnectionError("no network")):
    for f in (lambda: websearch.weather_text("Пусан"), lambda: websearch.wiki_search("Пусан")):
        try:
            f()
            raise AssertionError("без сети должно быть ConnectionError")
        except ConnectionError:
            pass

# ничего из запрещённого для продажи
src = (Path(websearch.__file__)).read_text(encoding="utf-8")
assert "ddgs" not in src and "open-meteo" not in src.lower()
print("OK")
