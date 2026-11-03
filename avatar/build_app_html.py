"""Собирает app.html: шаблон окна + персонаж из avatar.html (рисунок правится в одном месте)."""
from pathlib import Path
here = Path(__file__).parent
av = (here / "avatar.html").read_text(encoding="utf-8")
svg = av[av.index("<svg"):av.index("</svg>") + 6]
css = av[av.index("<style>") + 7:av.index("</style>")]
css = css[css.index("/* дыхание */"):]
tpl = (here / "app_template.html").read_text(encoding="utf-8")
(here / "app.html").write_text(tpl.replace("{{SVG}}", svg).replace("{{CHARCSS}}", css), encoding="utf-8")
print("app.html собран")
