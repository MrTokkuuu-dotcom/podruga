"""Показывает модели Gemini, доступные по твоему ключу. Имя нужной вставь в config.yaml."""
import os

from google import genai

from config import load_config

load_config()  # подхватывает ключ из .env
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
for m in client.models.list():
    if "flash" in m.name:
        print(m.name.removeprefix("models/"))
