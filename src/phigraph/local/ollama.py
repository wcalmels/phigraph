from __future__ import annotations

import json
from urllib.request import Request, urlopen


class OllamaClient:
    """Small optional client for a locally running Ollama instance."""

    def __init__(
        self,
        model: str,
        endpoint: str = "http://127.0.0.1:11434/api/chat",
        timeout: float = 120.0,
    ):
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout

    def chat(self, messages: list[dict], *, json_mode: bool = False) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))
