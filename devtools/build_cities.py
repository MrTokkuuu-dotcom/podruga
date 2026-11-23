"""Список городов для погоды без интернета-геокодера: из GeoNames cities15000 (CC BY 4.0, коммерческое
использование разрешено с указанием GeoNames). Запуск: python devtools/build_cities.py cities15000.txt
→ cities.tsv.gz: имя (в нижнем регистре) \t широта \t долгота — по одной строке на имя, самый большой город."""
import gzip
import re
import sys
from pathlib import Path

MIN_POP = 30000
KEEP = re.compile(r"^[A-Za-z .'-]+$|[А-Яа-яЁё]|[가-힣]")   # латиница, кириллица, хангыль


def main(src: str) -> None:
    best: dict[str, tuple[int, float, float]] = {}
    for line in open(src, encoding="utf-8"):
        f = line.rstrip("\n").split("\t")
        pop = int(f[14] or 0)
        if pop < MIN_POP:
            continue
        lat, lon = float(f[4]), float(f[5])
        names = {f[1], f[2], *f[3].split(",")}
        for n in names:
            n = n.strip()
            if 2 <= len(n) <= 40 and KEEP.search(n):
                k = n.lower().replace("ё", "е")
                if k not in best or best[k][0] < pop:
                    best[k] = (pop, lat, lon)
    out = Path(__file__).resolve().parent.parent / "cities.tsv.gz"
    with gzip.open(out, "wt", encoding="utf-8") as g:
        for k in sorted(best):
            g.write(f"{k}\t{best[k][1]:.3f}\t{best[k][2]:.3f}\n")
    print(f"{len(best)} имён → {out} ({out.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    main(sys.argv[1])
