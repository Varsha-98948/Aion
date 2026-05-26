"""Local Ollama client for Aion response generation.

Local-first AI keeps user documents and prompts on the user's machine. The
tradeoff is that local models may be slower or less capable than hosted models,
but they offer stronger privacy and predictable ownership of the data path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass(slots=True)
class OllamaGenerationConfig:
    """Configuration for one Ollama generation request."""

    model: str = "mistral"
    temperature: float = 0.2
    timeout_seconds: int = 120


class OllamaClient:
    """Minimal REST client for a local Ollama server.

    Ollama exposes local LLMs over HTTP. Keeping this client separate from RAG
    orchestration preserves a clean boundary: generation transport can change
    later without rewriting retrieval, prompt building, or vector indexing.
    """

    def __init__(
        self,
        model: str = "mistral",
        base_url: str = "http://localhost:11434",
        timeout_seconds: int = 120,
        temperature: float = 0.2,
    ) -> None:
        self.config = OllamaGenerationConfig(
            model=model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )
        self.base_url = base_url.rstrip("/")

    def health_check(self) -> bool:
        """Return True when the local Ollama server is reachable."""

        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=min(self.config.timeout_seconds, 10),
            )
            return response.ok
        except requests.RequestException:
            return False

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Send a prompt to Ollama and return the generated response text."""

        payload = self._build_generate_payload(
            prompt=prompt,
            system_prompt=system_prompt,
            options=options,
        )
        response_payload = self._post_generate(payload)
        generated_text = response_payload.get("response", "")

        if not isinstance(generated_text, str):
            raise RuntimeError("Ollama returned an invalid response payload.")

        return generated_text.strip()

    def _build_generate_payload(
        self,
        prompt: str,
        system_prompt: str | None,
        options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build the JSON body expected by Ollama's generate endpoint.

        Example Ollama API request:
            {
              "model": "mistral",
              "prompt": "Retrieved context: ...",
              "system": "Answer only from context.",
              "stream": false,
              "options": {"temperature": 0.2}
            }
        """

        request_options = {"temperature": self.config.temperature}
        if options:
            request_options.update(options)

        payload: dict[str, Any] = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": request_options,
        }

        if system_prompt:
            payload["system"] = system_prompt

        return payload

    def _post_generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute the HTTP generation request with clear error handling."""

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise RuntimeError(
                "Ollama generation failed. Confirm Ollama is running locally "
                f"and the '{self.config.model}' model is available."
            ) from error

        response_payload = response.json()
        if not isinstance(response_payload, dict):
            raise RuntimeError("Ollama returned a non-object JSON response.")

        return response_payload


__all__ = ["OllamaClient", "OllamaGenerationConfig"]
