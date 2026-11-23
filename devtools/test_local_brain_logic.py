"""Логика своего мозга без самой модели: недокачанная модель, окно истории, язык продолжений.
Запуск: ~/Podruga/venv/bin/python devtools/test_local_brain_logic.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from local_brain import LocalBrain, model_complete  # noqa: E402

# 2) недокачанная модель: из двух кусков есть один — не «готова», надо докачать
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    (d / "config.json").write_text("{}")
    (d / "model.safetensors.index.json").write_text(json.dumps({"weight_map": {
        "a": "model-00001-of-00002.safetensors", "b": "model-00002-of-00002.safetensors"}}))
    (d / "model-00001-of-00002.safetensors").write_bytes(b"x")
    assert not model_complete(d), "один кусок из двух — модель не готова"
    (d / "model-00002-of-00002.safetensors").write_bytes(b"x")
    assert model_complete(d)
    assert not model_complete(d / "нет")

# без модели: объект без потока, только разбор сообщений
b = LocalBrain.__new__(LocalBrain)
b._stable, b._anchor = "характер", None
b.lang_of = lambda: "ko"
b.history_max = 20


def hist(n, start=0):
    return [{"role": "user" if i % 2 == 0 else "model", "text": f"реплика {i}"} for i in range(start, start + n)]


# 6) история полна и сдвигается по одной реплике — начало окна держится, кэш истории продолжает подходить
w1 = b._window(hist(20, 0))
w2 = b._window(hist(20, 2))          # две старые реплики выпали, две новые пришли
assert w1[0] == w2[0], "начало окна не должно сдвигаться на каждой реплике"
assert w2[-1]["text"] == "реплика 21"
for k in range(4, 22, 2):            # когда начало окна выпало — окно прыгает сразу на половину
    w = b._window(hist(20, k))
    assert w[0]["text"] == f"реплика {w[0]['text'].split()[1]}" and w[0]["role"] == "user"
    assert len(w) <= 20
assert len(b._window(hist(20, 40))) <= 12, "после прыжка окно короче — есть куда расти"

# 11) продолжение после корейской фразы — с корейской припиской
msgs = b._messages([], "x")
assert msgs[0]["role"] == "system"
assert "ПО-КОРЕЙСКИ" in b._once_text("## Сейчас\nвечер", "Скажи что-нибудь")
print("OK")
