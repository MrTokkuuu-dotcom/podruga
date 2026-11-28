"""Свой мозг на Mac: Gemma 4 E4B (4 бита) через mlx-lm, без Google и без интернета.
Тот же набор методов, что у GeminiBrain (stream_reply, say_once, chat, search, unload, preload),
поэтому main.py, memory.py и initiative.py работают с ним как с облачным.

Вся работа с моделью — в одном своём потоке (MLX не любит, когда видеочип дёргают из разных потоков),
запросы идут по очереди. Подсказка-«характер» считается один раз и лежит в кэше: без кэша ответ ждал бы
6–13 с, с кэшем первое слово ~0,3–0,7 с. История разговора тоже дописывается к кэшу, пока она только растёт."""
import copy
import gc
import importlib
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from local_prompt import turn_text

MODEL_REPO = "lmstudio-community/gemma-4-E4B-it-MLX-4bit"
PKGS = ["mlx==0.32.4", "mlx-lm==0.32.2", "transformers==5.24.0"]
STAMP = ".local_brain_failed"


NEED_RAM = 15 * 1024 ** 3          # Mac на 16 ГБ показывает 16; на 8 ГБ модель (5,9 ГБ) задушит систему
NEED_DISK = 8 * 1024 ** 3          # 6,4 ГБ модели + запас


def model_complete(d: Path) -> bool:
    """Модель скачана целиком: есть config.json и все куски весов из model.safetensors.index.json."""
    d = Path(d)
    if not (d / "config.json").exists():
        return False
    index = d / "model.safetensors.index.json"
    if index.exists():
        try:
            import json
            parts = set(json.loads(index.read_text(encoding="utf-8"))["weight_map"].values())
        except (ValueError, KeyError, OSError):
            return False
        return bool(parts) and all((d / f).exists() for f in parts)
    return (d / "model.safetensors").exists()


def can_run(home: Path, machine: str | None = None, memsize: int | None = None, free: int | None = None):
    """(можно ли, почему) — свой мозг только на Mac с чипом Apple, от 16 ГБ памяти и с местом под модель."""
    import platform
    import shutil
    if machine is None:
        if sys.platform != "darwin":
            return False, "не Mac"
        machine = platform.machine()
    if machine != "arm64":
        return False, "нужен Mac на чипе Apple (M1 и новее)"
    if memsize is None:
        try:
            memsize = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
        except (ValueError, OSError):
            memsize = 0
    if memsize < NEED_RAM:
        return False, f"мало памяти ({memsize / 1024 ** 3:.0f} ГБ, нужно 16)"
    have = model_complete(Path(home) / "models" / "brain" / MODEL_REPO.split("/")[-1])
    if free is None:
        p = Path(home)
        while not p.exists() and p != p.parent:
            p = p.parent
        free = shutil.disk_usage(p).free
    if not have and free < NEED_DISK:
        return False, f"мало места на диске ({free / 1024 ** 3:.0f} ГБ, нужно 8)"
    return True, "ок"


def fresh_part(system: str) -> str:
    """Из подсказки для Google — только свежее (время, события, режим, возвращение): характер уже в кэше."""
    i = system.rfind("## Сейчас\n")
    return system[i:] if i >= 0 else system


class NeedGoogle(RuntimeError):
    """Нужны свежие данные (курс, новости), которых нет в разрешённых для продажи бесплатных источниках."""


class LocalBrain:
    def __init__(self, home: Path, notify=print, repo: str = MODEL_REPO):
        self.home = Path(home)
        self.repo = repo
        self.dir = self.home / "models" / "brain" / repo.split("/")[-1]
        self.notify = notify
        self.ready = threading.Event()
        self.ever = False                           # хоть раз загрузилась (дальше грузится сама по запросу)
        self.failed = False
        self._failed_at = 0.0
        self.lang_of = lambda: "ru"                 # main подставит язык его последней фразы
        self.history_max = 20                       # сколько реплик держит main (его deque)
        self._anchor = None                         # с какой реплики начинается окно истории
        self.model = self.tok = None
        self._stable: str | None = None            # какой характер нужен сейчас
        self._pre_text = None                       # для какого характера посчитан кэш
        self._pre_ids = self._pre_cache = None
        self._hist_ids = self._hist_cache = None    # кэш «характер + история» с прошлого раза
        self._jobs: queue.Queue = queue.Queue()
        threading.Thread(target=self._worker, name="local-brain", daemon=True).start()
        self._jobs.put(("load", None, None))

    # ---------- снаружи ----------
    def set_system(self, stable: str) -> None:
        """Новый характер/память. Кэш пересчитается в фоне (~4 с), старый не «залипает»."""
        if stable != self._stable:
            self._stable = stable
            self._jobs.put(("prefix", None, None))

    def stream_reply(self, system: str, history: list[dict], wav: bytes | None = None, text: str | None = None,
                     image: bytes | None = None, image_mime: str = "image/jpeg", lang: str | None = None):
        """system — свежая часть (время, события, режим) или вся подсказка для Google — из неё берётся
        только свежее, от «## Сейчас». Характер уже в кэше через set_system."""
        if wav:
            raise ValueError("свой мозг понимает только текст: сначала расшифруй речь")
        if image:
            raise ValueError("свой мозг пока не смотрит на картинки")
        lang = lang or self.lang_of()
        yield from self._run(self._messages(history, turn_text(text or "", lang, fresh_part(system))), 200, 0.8)

    def say_once(self, system: str, instruction: str) -> str:
        return "".join(self._run(self._messages([], self._once_text(system, instruction)), 120, 0.8)).strip()

    def _once_text(self, system: str, instruction: str) -> str:
        """Продолжение/приветствие — на языке его последней фразы."""
        return turn_text(instruction, self.lang_of(), fresh_part(system))

    def chat(self, messages: list[dict], options: dict | None = None) -> str:
        """Для памяти: выписать факты, сжать. Без характера и кэша."""
        text = "\n\n".join(m["content"] for m in messages)
        temp = (options or {}).get("temperature", 0.2)
        n = (options or {}).get("max_tokens", 400)
        static = (options or {}).get("static")             # неизменное начало подсказки (правила агента) — в кэш
        return "".join(self._run([{"role": "user", "content": text}], n, temp, cached=False, static=static))

    def search(self, query: str, context: str = "") -> str:
        """Погода (MET Norway) или справка (Википедия) → своя модель выбирает главное.
        Курс/новости/цены — NeedGoogle (бесплатного источника, который можно продавать, нет).
        Нет сети — ConnectionError (main честно скажет)."""
        import re
        from websearch import is_weather, needs_google, weather_city, weather_text, wiki_search
        if needs_google(query):
            raise NeedGoogle(query)
        found = ""
        if is_weather(query):
            m = re.search(r"в городе (.+?)\.", context)
            home = m.group(1) if m else "Пусан"
            city = None
            for w in re.findall(r"[\w-]{2,}", query):
                if w[:4].lower() == home[:4].lower():
                    break                             # «в Пусане» — свой город
                city = weather_city(w)
                if city:
                    break
            found = weather_text(*city) if city else weather_text(home)
        else:
            rows = wiki_search(query)
            found = "\n".join(f"- {r['title']}: {r['body']}" for r in rows if r["body"])[:3000]
            if not found:
                return "В Википедии про это ничего не нашлось."
        return self.chat([{"role": "user", "content":
                           f"{context}\nВопрос: {query}\nЧто нашлось:\n{found}\n\n"
                           "Выпиши по-русски только факты, которые отвечают на вопрос: 1–3 короткие строки, с цифрами, "
                           "если есть, без markdown и звёздочек. Чего нет в найденном — так и напиши одной фразой, "
                           "не выдумывай."}], {"temperature": 0.2, "max_tokens": 120}).strip()

    def unload(self) -> bool:
        """Освободить память (сон, игра). Следующий запрос сам загрузит модель (~3 с)."""
        return self._call("unload")

    def preload(self, *a, **k) -> bool:
        return self._call("load")

    # ---------- очередь ----------
    def _call(self, kind: str, timeout: float = 120) -> bool:
        done: queue.Queue = queue.Queue()
        self._jobs.put((kind, None, done))
        try:
            return done.get(timeout=timeout)[1] is True
        except queue.Empty:
            return False

    def _run(self, msgs, max_tokens, temp, cached=True, static=None):
        out: queue.Queue = queue.Queue()
        cancel = threading.Event()
        self._jobs.put(("gen", (msgs, max_tokens, temp, cached, cancel, static), out))
        try:
            while True:
                kind, val = out.get(timeout=180)
                if kind == "text":
                    if val:
                        yield val
                elif kind == "err":
                    raise val
                else:
                    return
        finally:
            cancel.set()                        # его перебили или ответ бросили — модель останавливается

    def _messages(self, history: list[dict], last: str) -> list[dict]:
        if self._stable is None:
            raise RuntimeError("нет подсказки: сначала set_system")
        merged: list[dict] = []
        for h in self._window(history):
            role = "assistant" if h["role"] == "model" else "user"
            if merged and merged[-1]["role"] == role:
                merged[-1] = {"role": role, "content": merged[-1]["content"] + "\n" + h["text"]}
            else:
                merged.append({"role": role, "content": h["text"]})
        if merged and merged[0]["role"] == "assistant":
            merged.insert(0, {"role": "user", "content": "(начало разговора)"})
        if merged and merged[-1]["role"] == "user":
            merged.append({"role": "assistant", "content": "(не расслышала)"})
        return [{"role": "system", "content": self._stable}] + merged + [{"role": "user", "content": last}]

    def _window(self, history: list[dict]) -> list[dict]:
        """Окно истории с устойчивым началом. main выбрасывает по одной старой реплике — если начинать каждый раз
        с самой старой, кэш истории никогда не подходит (1,1 с на ответ). Держим начало, пока оно не выпало,
        потом прыгаем сразу на середину — так почти все ответы идут через быстрый путь (~0,3 с)."""
        n = len(history)
        key = lambda h: (h["role"], h["text"])
        idx = None
        if self._anchor is not None:
            idx = next((i for i, h in enumerate(history) if key(h) == self._anchor), None)
        if idx is None:
            idx = n // 2 if n >= self.history_max else 0
            while idx < n and history[idx]["role"] != "user":
                idx += 1
            if idx >= n:
                idx = 0
            self._anchor = key(history[idx]) if n else None
        return list(history)[idx:]

    def _worker(self):
        while True:
            kind, args, out = self._jobs.get()
            try:
                if kind == "load":
                    res = self._load()
                elif kind == "unload":
                    res = self._unload()
                elif kind == "prefix":
                    if any(j[0] == "gen" for j in list(self._jobs.queue)):
                        self._jobs.put((kind, args, out))     # сначала ответы, характер — потом
                        continue
                    res = self._prefix() if self.model is not None else True
                else:
                    self._gen(*args, out)
                    continue
                if out is not None:
                    out.put(("done", res))
            except Exception as e:
                if kind == "load":
                    self.failed = True
                    print(f"[мозг] свой мозг не включился: {e}", flush=True)
                else:
                    print(f"[мозг] свой: ошибка ({kind}): {e}", flush=True)
                if out is not None:
                    out.put(("err", e) if kind == "gen" else ("done", False))

    # ---------- модель (только в своём потоке) ----------
    def _install(self) -> bool:
        uv = self.home / "bin" / "uv"
        if os.environ.get("PODRUGA_BUNDLED") or not uv.exists():
            return False
        stamp = self.home / STAMP
        if stamp.exists() and stamp.read_text().strip() == " ".join(PKGS):
            return False                                   # эти версии уже не встали — не мучаем
        print("[мозг] ставлю свой мозг (mlx-lm)…", flush=True)
        r = subprocess.run([str(uv), "pip", "install", "--python", sys.executable, "-q", *PKGS],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[мозг] свой мозг не встал:\n{r.stderr[-800:]}", flush=True)
            stamp.write_text(" ".join(PKGS))
            return False
        return True

    def _load(self) -> bool:
        if self.model is not None:
            return True
        if self.failed:
            if time.monotonic() - self._failed_at < 600:
                return False                                # не встала — пробуем снова не чаще раза в 10 минут
            self.failed = False
        try:
            return self._load_now()
        except Exception:
            self.failed, self._failed_at = True, time.monotonic()
            raise

    def _load_now(self) -> bool:
        try:
            importlib.import_module("mlx_lm")
        except ImportError:
            if not self._install():
                raise RuntimeError("mlx-lm недоступен")
            importlib.invalidate_caches()
        import mlx.core as mx
        from mlx_lm import load
        self._mx = mx
        mx.set_cache_limit(512 * 1024 * 1024)        # запас видеочипа после ответа — не больше 0,5 ГБ (было до ~1,2)
        if not model_complete(self.dir):                    # нет или недокачана — snapshot_download докачает
            self.notify("Качаю свой мозг (~6,4 ГБ, один раз). Пока думаю по-старому.")
            from huggingface_hub import snapshot_download
            self.dir.mkdir(parents=True, exist_ok=True)
            snapshot_download(self.repo, local_dir=str(self.dir))
            self.notify("Свой мозг скачан — теперь думаю сама, без интернета.")
        t0 = time.monotonic()
        self.model, self.tok = load(str(self.dir))
        print(f"[мозг] свой (Gemma 4 E4B) загружен за {time.monotonic() - t0:.1f} с, "
              f"память {mx.get_active_memory() / 1e9:.1f} ГБ", flush=True)
        if self._stable is not None:
            self._prefix()
        self.ever = True
        self.ready.set()
        return True

    def _unload(self) -> bool:
        if self.model is None:
            return True
        self.ready.clear()
        self.model = self.tok = None
        self._pre_text = self._pre_ids = self._pre_cache = self._hist_ids = self._hist_cache = None
        gc.collect()
        self._mx.clear_cache()
        print("[мозг] свой выгружен — память свободна", flush=True)
        return True

    def _template(self, msgs, gen_prompt=True) -> str:
        kw = dict(add_generation_prompt=gen_prompt, tokenize=False)
        try:
            return self.tok.apply_chat_template(msgs, enable_thinking=False, **kw)
        except TypeError:
            return self.tok.apply_chat_template(msgs, **kw)

    def _encode(self, text: str) -> list[int]:
        bos = getattr(self.tok, "bos_token", None)
        if bos and text.startswith(bos):
            return self.tok.encode(text, add_special_tokens=False)
        return self.tok.encode(text)

    def _feed(self, cache, ids):
        import gpu
        gpu.mark_own()
        mx = self._mx
        step = 512                                   # кусками, чтобы не раздувать пик памяти
        for i in range(0, len(ids), step):
            self.model(mx.array(ids[i:i + step])[None], cache=cache)
            mx.eval([c.state for c in cache])

    def _prefix(self) -> bool:
        """Кэш характера: шаблон до начала первого сообщения пользователя."""
        stable = self._stable
        if stable is None or stable == self._pre_text:
            return True
        from mlx_lm.models.cache import make_prompt_cache
        t0 = time.monotonic()
        base = self._template([{"role": "system", "content": stable}, {"role": "user", "content": "§"}], False)
        ids = self._encode(base[: base.index("§")])
        cache = make_prompt_cache(self.model)
        self._feed(cache, ids)
        self._pre_ids, self._pre_cache, self._pre_text = ids, cache, stable
        self._hist_ids = self._hist_cache = None
        print(f"[мозг] свой: характер в кэше ({len(ids)} ток) за {time.monotonic() - t0:.1f} с", flush=True)
        return True

    @staticmethod
    def _starts(ids, pre) -> bool:
        return pre is not None and len(ids) >= len(pre) and ids[: len(pre)] == pre

    def _prompt(self, msgs, ids):
        """(кэш, что ещё скормить): берём самый длинный готовый кэш, совпадающий с началом подсказки."""
        if msgs[0]["role"] != "system" or msgs[0]["content"] != self._pre_text or not self._starts(ids, self._pre_ids):
            return None, ids, 0
        hist = self._encode(self._template(msgs[:-1], False)) if len(msgs) > 2 else None
        if hist is None or not self._starts(ids, hist) or len(hist) <= len(self._pre_ids):
            return copy.deepcopy(self._pre_cache), ids[len(self._pre_ids):], len(self._pre_ids)
        if self._starts(hist, self._hist_ids):
            cache, done = copy.deepcopy(self._hist_cache), len(self._hist_ids)
        else:
            cache, done = copy.deepcopy(self._pre_cache), len(self._pre_ids)
        self._feed(cache, hist[done:])                   # дописываем только новые реплики истории
        self._hist_ids, self._hist_cache = hist, copy.deepcopy(cache)
        return cache, ids[len(hist):], done

    def _static_cache(self, static: str):
        """Кэш для неизменного начала подсказки без характера (правила агента «глаз и рук»): ~1500 ток один раз,
        а не на каждом шаге (журнал 29.11: каждый шаг 3,7 с, «из кэша 0»)."""
        from mlx_lm.models.cache import make_prompt_cache
        sc = getattr(self, "_statics", None)
        if sc is None:
            sc = self._statics = {}
        if static not in sc:
            base = self._template([{"role": "user", "content": static + "§"}], False)
            ids = self._encode(base[: base.index("§")])
            cache = make_prompt_cache(self.model)
            self._feed(cache, ids)
            if len(sc) >= 3:
                sc.pop(next(iter(sc)))
            sc[static] = (ids, cache)
        return sc[static]

    def _gen(self, msgs, max_tokens, temp, cached, cancel, static, out):
        import gpu
        gpu.mark_own()
        try:
            if self.model is None and not self._load():
                raise RuntimeError("свой мозг не загружен")
            from mlx_lm import stream_generate
            from mlx_lm.sample_utils import make_sampler
            t0 = time.monotonic()
            if cached:
                if self._pre_text is None:
                    self._prefix()
                elif self._stable != self._pre_text:
                    # память обновилась: этот ответ — со старым характером из кэша (сразу), новый посчитается
                    # после ответа. Раньше ответ ждал пересчёта ~6–7 с (журнал 29.11)
                    msgs = [{"role": "system", "content": self._pre_text}] + list(msgs[1:])
                    self._jobs.put(("prefix", None, None))
                ids = self._encode(self._template(msgs))
                cache, rest, reused = self._prompt(msgs, ids)
            else:
                ids = self._encode(self._template(msgs))
                cache, rest, reused = None, ids, 0
                if static and msgs and msgs[0]["content"].startswith(static):
                    pids, pc = self._static_cache(static)
                    if self._starts(ids, pids) and len(ids) > len(pids):
                        cache, rest, reused = copy.deepcopy(pc), ids[len(pids):], len(pids)
            first, n = None, 0
            kw = {"prompt_cache": cache} if cache is not None else {}
            for r in stream_generate(self.model, self.tok, rest, max_tokens=max_tokens,
                                     sampler=make_sampler(temp=temp, top_p=0.95), **kw):
                if cancel.is_set():
                    break
                n += 1
                if n % 32 == 0:
                    gpu.mark_own()
                if first is None:
                    first = time.monotonic() - t0
                out.put(("text", r.text))
            total = time.monotonic() - t0
            if first is not None and n > 1:
                print(f"[мозг] свой: первое слово {first:.2f} с, {n / max(total - first, 1e-3):.0f} ток/с, "
                      f"подсказка {len(ids)} ток (из кэша {reused})", flush=True)
            out.put(("end", None))
        except Exception as e:
            out.put(("err", e))
