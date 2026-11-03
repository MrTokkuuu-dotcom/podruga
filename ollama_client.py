"""Минимальный клиент Ollama: загрузить/выгрузить модель из видеокарты и спросить."""
import requests


class Ollama:
    def __init__(self, url: str, model: str):
        self.url = url.rstrip("/")
        self.model = model

    def is_up(self) -> bool:
        try:
            return requests.get(f"{self.url}/api/tags", timeout=3).ok
        except requests.RequestException:
            return False

    def unload(self) -> bool:
        """Освобождает видеопамять (keep_alive=0)."""
        try:
            r = requests.post(f"{self.url}/api/generate",
                              json={"model": self.model, "keep_alive": 0}, timeout=30)
            return r.ok
        except requests.RequestException:
            return False

    def preload(self, keep_alive: str = "24h") -> bool:
        """Загружает модель заранее, чтобы первый ответ не ждал загрузки."""
        try:
            r = requests.post(f"{self.url}/api/generate",
                              json={"model": self.model, "keep_alive": keep_alive}, timeout=180)
            return r.ok
        except requests.RequestException:
            return False

    def chat(self, messages: list[dict], options: dict | None = None) -> str:
        r = requests.post(f"{self.url}/api/chat", json={
            "model": self.model, "messages": messages, "stream": False,
            "keep_alive": "24h", "options": options or {},
        }, timeout=180)
        r.raise_for_status()
        return r.json()["message"]["content"]
