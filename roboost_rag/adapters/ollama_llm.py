"""LLM backed by a local Ollama server (by default the host's native install)."""

from __future__ import annotations

import logging
import re

import ollama

from roboost_rag.ports import LLMUnavailableError

log = logging.getLogger(__name__)

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class OllamaLLM:
    def __init__(
        self,
        host: str,
        model: str = "qwen3.5:9b",
        *,
        temperature: float = 0.1,
        timeout: float = 180.0,
        client: ollama.Client | None = None,
    ):
        self.host = host
        self.model = model
        self.temperature = temperature
        self.client = client or ollama.Client(host=host, timeout=timeout)

    def generate(self, system: str, prompt: str) -> str:
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                think=False,
                options={"temperature": self.temperature},
            )
        except Exception as exc:  # connection refused, timeout, model missing...
            raise LLMUnavailableError(f"Ollama ({self.host}) no disponible: {exc}") from exc
        return _THINK_BLOCK.sub("", response.message.content or "").strip()

    def check_model(self) -> str | None:
        return missing_model_message(self.client, self.host, self.model)


def missing_model_message(client: ollama.Client, host: str, model: str) -> str | None:
    """None if `model` is available in Ollama; otherwise a human-readable problem description."""
    try:
        names = {m.model for m in client.list().models}
    except Exception as exc:
        return f"Ollama no es accesible en {host} ({exc}). ¿Está Ollama en ejecución?"
    if model in names or f"{model}:latest" in names:
        return None
    return f"El modelo '{model}' no está descargado en Ollama ({host}). Ejecuta: ollama pull {model}"
