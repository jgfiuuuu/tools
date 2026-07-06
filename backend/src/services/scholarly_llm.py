"""Shared OpenAI-compatible helper for scholarly LLM calls and usage tracking."""

from __future__ import annotations

import json
import logging
import math
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from openai import OpenAI

from config import Configuration
from services.scholarly_contracts import default_llm_usage

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ScholarlyLLMResponse:
    """Normalized LLM response payload plus usage metadata."""

    text: str
    usage: dict[str, Any]


class ScholarlyLLMService:
    """Thin OpenAI-compatible wrapper with stable usage accounting."""

    def __init__(self, config: Configuration) -> None:
        self.config = config
        self._client = self._build_client()
        self._disabled = False
        self._reachability_checked = False

    def available(self) -> bool:
        """Return whether an OpenAI-compatible client is configured."""

        if not self._reachability_checked:
            self._reachability_checked = True
            if not self._endpoint_reachable():
                self._disabled = True
        return (
            not self._disabled
            and self._client is not None
            and bool(self.config.resolved_model())
        )

    def complete_text(
        self,
        *,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 1400,
        timeout_seconds: float = 8.0,
        disable_on_error: bool = True,
    ) -> ScholarlyLLMResponse:
        """Generate a text completion and capture usage."""

        client = self._require_client()
        try:
            response = client.chat.completions.create(
                model=self.config.resolved_model(),
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout_seconds,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception:
            if disable_on_error:
                self._disabled = True
            raise
        text = ""
        if response.choices:
            text = str(response.choices[0].message.content or "").strip()
        usage = self._normalize_usage(
            response=response,
            stage=stage,
            input_fallback=f"{system_prompt}\n\n{user_prompt}",
            output_fallback=text,
        )
        return ScholarlyLLMResponse(text=text, usage=usage)

    def complete_json(
        self,
        *,
        stage: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        temperature: float = 0.0,
        max_tokens: int = 1800,
        timeout_seconds: float = 8.0,
        disable_on_error: bool = True,
    ) -> tuple[dict[str, Any] | None, dict[str, Any], str]:
        """Generate JSON-only content and parse it best-effort."""

        response = self.complete_text(
            stage=stage,
            system_prompt=system_prompt,
            user_prompt=json.dumps(user_payload, ensure_ascii=False),
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            disable_on_error=disable_on_error,
        )
        payload = self._extract_json_payload(response.text)
        return payload, response.usage, response.text

    def _require_client(self) -> OpenAI:
        client = self._client
        if client is None or not self.config.resolved_model():
            raise RuntimeError("No OpenAI-compatible scholarly LLM client is configured.")
        return client

    def _build_client(self) -> OpenAI | None:
        model = self.config.resolved_model()
        if not model:
            return None

        provider = (self.config.llm_provider or "").strip().lower()
        api_key = self.config.llm_api_key
        base_url = self.config.llm_base_url
        if provider == "ollama":
            base_url = self.config.sanitized_ollama_url()
            api_key = api_key or "ollama"
        elif provider == "lmstudio":
            base_url = self.config.lmstudio_base_url
            api_key = api_key or "lmstudio"
        elif not base_url:
            return None

        try:
            return OpenAI(base_url=base_url, api_key=api_key or "placeholder")
        except Exception as exc:  # pragma: no cover - trivial client construction
            logger.warning("Failed to initialize scholarly LLM client: %s", exc)
            return None

    def _endpoint_reachable(self) -> bool:
        if self._client is None:
            return False
        base_url = self.config.llm_base_url
        provider = (self.config.llm_provider or "").strip().lower()
        if provider == "ollama":
            base_url = self.config.sanitized_ollama_url()
        elif provider == "lmstudio":
            base_url = self.config.lmstudio_base_url
        if not base_url:
            return True

        parsed = urlparse(base_url)
        host = parsed.hostname
        port = parsed.port
        if not host or host not in {"127.0.0.1", "localhost"} or not port:
            return True
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except OSError:
            return False

    @staticmethod
    def _extract_json_payload(text: str) -> dict[str, Any] | None:
        if not text:
            return None
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _normalize_usage(
        self,
        *,
        response: Any,
        stage: str,
        input_fallback: str,
        output_fallback: str,
    ) -> dict[str, Any]:
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        completion_tokens = (
            int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        )
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0) if usage else 0

        if not prompt_tokens:
            prompt_tokens = self._estimate_tokens(input_fallback)
        if not completion_tokens and output_fallback:
            completion_tokens = self._estimate_tokens(output_fallback)
        if not total_tokens:
            total_tokens = prompt_tokens + completion_tokens

        payload = default_llm_usage()
        payload["input_tokens"] = prompt_tokens
        payload["output_tokens"] = completion_tokens
        payload["total_tokens"] = total_tokens
        if stage not in payload["by_stage"]:
            payload["by_stage"][stage] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
        payload["by_stage"][stage] = {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        return payload

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        compact = (text or "").strip()
        if not compact:
            return 0
        return max(1, int(math.ceil(len(compact) / 4)))
