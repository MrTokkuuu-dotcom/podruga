"""Поиск без Google — только из источников, которые разрешено использовать в платном приложении:
- погода: MET Norway (api.met.no) — CC BY 4.0, коммерческое использование разрешено, нужно указать источник
  и назвать приложение в User-Agent;
- города: свой список из GeoNames (cities.tsv.gz, CC BY 4.0) — без запросов в интернет;
- справки: Википедия — тексты CC BY-SA 4.0, коммерческое использование разрешено со ссылкой на источник.
Курс, новости, цены — только через Google (ключ пользователя): бесплатного источника, который можно продавать, нет.
Нет сети — ConnectionError, она честно скажет."""
import gzip
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
USER_AGENT = "Podruga/29 (+https://github.com/MrTokkuuu-dotcom/podruga)"   # требование MET Norway и Википедии
CREDIT_WEATHER = "Данные о погоде: MET Norway (CC BY 4.0)."

WEATHER_WORDS = ("погод", "дожд", "снег", "температур", "холодно", "жарко", "зонт", "weather", "rain", "날씨", "비 와")
FRESH_WORDS = ("курс", "новост", "цена", "цены", "стоит", "сколько стоит", "счёт", "счет матча", "акци", "биткоин",
               "расписани", "пробк", "exchange rate", "news", "price", "환율", "뉴스", "가격")


def is_weather(query: str) -> bool:
    q = query.lower()
    return any(w in q for w in WEATHER_WORDS)


def needs_google(query: str) -> bool:
    """Свежие данные (курс, новости, цены), которых нет в разрешённых бесплатных источниках."""
    q = query.lower()
    return not is_weather(q) and any(w in q for w in FRESH_WORDS)


# ---------- города ----------
_CITIES: dict[str, tuple[float, float]] | None = None
_NOT_CITY = {"какая", "какой", "какие", "какое", "что", "где", "когда", "сколько", "завтра", "сегодня", "погода",
             "погоду", "будет", "скажи", "расскажи", "узнай", "глянь", "посмотри", "найди", "сейчас", "аня",
             "подруга", "weather", "what", "tomorrow", "today", "will", "how", "кака"}


def _cities() -> dict[str, tuple[float, float]]:
    global _CITIES
    if _CITIES is None:
        _CITIES = {}
        with gzip.open(ROOT / "cities.tsv.gz", "rt", encoding="utf-8") as f:
            for line in f:
                k, lat, lon = line.rstrip("\n").split("\t")
                _CITIES[k] = (float(lat), float(lon))
    return _CITIES


def weather_city(word: str):
    """«Пусане» → ('пусан', широта, долгота); не город — None. Падежи: пробуем начальную форму."""
    w = word.strip().lower().replace("ё", "е")
    if len(w) < 2 or w in _NOT_CITY:
        return None
    cands = [w]
    if len(w) > 3 and w[-1] in "еуаиюяыо":
        cands += [w[:-1], w[:-1] + "а", w[:-1] + "ь", w[:-1] + "я"]
    if len(w) > 4 and w.endswith(("ом", "ой", "ем", "ью")):
        cands += [w[:-2], w[:-2] + "а", w[:-2] + "ь"]
    db = _cities()
    for c in cands:
        if c in db and c not in _NOT_CITY:
            return (c, *db[c])
    return None


# ---------- погода ----------
_SYMBOL = {"clearsky": "ясно", "fair": "почти ясно", "partlycloudy": "переменная облачность", "cloudy": "пасмурно",
           "fog": "туман", "lightrain": "небольшой дождь", "rain": "дождь", "heavyrain": "сильный дождь",
           "lightrainshowers": "небольшой ливень", "rainshowers": "ливень", "heavyrainshowers": "сильный ливень",
           "lightsleet": "мокрый снег", "sleet": "мокрый снег", "heavysleet": "мокрый снег",
           "lightsnow": "небольшой снег", "snow": "снег", "heavysnow": "сильный снег",
           "lightsnowshowers": "снегопад", "snowshowers": "снегопад", "heavysnowshowers": "сильный снегопад"}


def _sky(code: str) -> str:
    base = code.split("_")[0]
    if "thunder" in base:
        return "гроза"
    return _SYMBOL.get(base, "облачно")


def weather_text(city: str, lat: float | None = None, lon: float | None = None, timeout: float = 8) -> str:
    """«Погода, Пусан: сейчас 16°, морось. 24.11: от 9° до 15°, ясно, осадки 0 мм…» Нет сети — ConnectionError."""
    import requests
    if lat is None:
        found = weather_city(city)
        if not found:
            raise ConnectionError(f"не знаю город {city}")
        _, lat, lon = found
    try:
        r = requests.get("https://api.met.no/weatherapi/locationforecast/2.0/compact", timeout=timeout,
                         params={"lat": round(lat, 2), "lon": round(lon, 2)}, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        series = r.json()["properties"]["timeseries"]
    except (requests.RequestException, ValueError, KeyError) as e:
        raise ConnectionError(f"погода недоступна: {e}") from e
    tz = timezone(timedelta(hours=int(lon / 15 + 0.5)))        # местное время города (примерно, по долготе)
    now = series[0]["data"]
    t_now = round(now["instant"]["details"]["air_temperature"])
    sky_now = _sky((now.get("next_1_hours") or now.get("next_6_hours") or {}).get("summary", {}).get("symbol_code", ""))
    days: dict[str, dict] = defaultdict(lambda: {"t": [], "sky": Counter(), "mm": 0.0})
    for p in series:
        t = datetime.fromisoformat(p["time"].replace("Z", "+00:00")).astimezone(tz)
        d = days[t.strftime("%d.%m")]
        d["t"].append(p["data"]["instant"]["details"]["air_temperature"])
        six = p["data"].get("next_6_hours")
        if six and t.hour in (0, 6, 12, 18):
            d["mm"] += six.get("details", {}).get("precipitation_amount", 0.0)
            if t.hour in (6, 12):
                d["sky"][_sky(six["summary"]["symbol_code"])] += 1
    parts = []
    for day, d in list(days.items())[:3]:
        sky = d["sky"].most_common(1)[0][0] if d["sky"] else sky_now
        parts.append(f"{day}: от {round(min(d['t']))}° до {round(max(d['t']))}°, {sky}, осадки {d['mm']:.0f} мм")
    return f"Погода, {city.capitalize()}: сейчас {t_now}°, {sky_now}. " + "; ".join(parts) + f". {CREDIT_WEATHER}"


# ---------- справки ----------
def wiki_search(query: str, lang: str = "ru", max_results: int = 3, timeout: float = 8) -> list[dict]:
    """[{title, body, href}] из Википедии (CC BY-SA 4.0). Нет сети — ConnectionError."""
    import requests
    base = f"https://{lang}.wikipedia.org/w/api.php"
    h = {"User-Agent": USER_AGENT}
    try:
        s = requests.get(base, timeout=timeout, headers=h, params={
            "action": "query", "list": "search", "srsearch": query, "srlimit": max_results, "format": "json"}).json()
        titles = [x["title"] for x in s.get("query", {}).get("search", [])]
        if not titles:
            return []
        e = requests.get(base, timeout=timeout, headers=h, params={
            "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "exchars": 600,
            "titles": "|".join(titles), "format": "json"}).json()
    except (requests.RequestException, ValueError) as err:
        raise ConnectionError(f"Википедия недоступна: {err}") from err
    pages = {p["title"]: p.get("extract", "") for p in e.get("query", {}).get("pages", {}).values()}
    return [{"title": t, "body": re.sub(r"\s+", " ", pages.get(t, "")).strip(),
             "href": f"https://{lang}.wikipedia.org/wiki/{t.replace(' ', '_')}"} for t in titles if pages.get(t)]
