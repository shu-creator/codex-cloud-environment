"""OpenAI Responses API adapter for LLM extraction."""
from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from fnl_builder.llm.adapter import PromptConfig
from fnl_builder.llm.response_parser import parse_llm_response
from fnl_builder.parse.tour_header import normalize_tour_header_candidate
from fnl_builder.shared.errors import LLMError
from fnl_builder.shared.types import LLMItem, TourHeaderData

_OPENAI_ENDPOINT = "https://api.openai.com/v1/responses"
_DEFAULT_MODEL = "gpt-5.2"
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_BASE_DELAY = 1.0
_DEFAULT_RETRY_MAX_DELAY = 30.0
_DEFAULT_MAX_OUTPUT_TOKENS = 16384
_DEFAULT_TIMEOUT = 600
_RETRYABLE_HTTP_CODES = frozenset({429, 500, 502, 503, 504})

SleepFn = Callable[[float], None]


def _get_retry_delay(
    attempt: int,
    base_delay: float = _DEFAULT_RETRY_BASE_DELAY,
    max_delay: float = _DEFAULT_RETRY_MAX_DELAY,
    retry_after: float | None = None,
) -> float:
    """Calculate retry delay with exponential backoff and jitter."""
    if retry_after is not None and retry_after > 0:
        return min(retry_after, max_delay)
    delay = min(base_delay * (2**attempt), max_delay)
    jitter = delay * random.uniform(0, 0.25)
    return float(delay + jitter)


def _is_retryable_error(exc: Exception) -> tuple[bool, float | None]:
    """Classify whether an exception is retryable and extract Retry-After."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in _RETRYABLE_HTTP_CODES:
            retry_after: float | None = None
            ra_header = exc.headers.get("Retry-After") if exc.headers else None
            if ra_header:
                try:
                    retry_after = float(ra_header)
                except (ValueError, TypeError):
                    pass
            return True, retry_after
        return False, None
    if isinstance(exc, (urllib.error.URLError, TimeoutError)):
        return True, None
    return False, None


def _load_schema() -> dict[str, object] | None:
    """Load the JSON Schema for structured output enforcement."""
    from importlib import resources

    try:
        ref = resources.files("fnl_builder.llm").joinpath("schema.json")
        text = ref.read_text(encoding="utf-8")
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        return None  # pragma: no cover
    except Exception:
        return None


@dataclass
class OpenAIAdapter:
    """LLM adapter using OpenAI Responses API with retry and JSON Schema."""

    api_key: str = ""
    model: str = ""
    endpoint: str = _OPENAI_ENDPOINT
    max_retries: int = _DEFAULT_MAX_RETRIES
    max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS
    timeout: int = _DEFAULT_TIMEOUT
    _schema: dict[str, object] | None = field(default=None, repr=False)
    _sleep_fn: SleepFn = field(default=time.sleep, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = os.environ.get("OPENAI_API_KEY", "")
        if not self.model:
            self.model = os.environ.get("OPENAI_MODEL", _DEFAULT_MODEL)
        if self._schema is None:
            self._schema = _load_schema()

    def extract_remarks(
        self,
        text: str,
        pages: list[object],
        prompts: PromptConfig,
    ) -> list[LLMItem]:
        """Extract remarks by calling OpenAI API.

        Args:
            text: Pre-built user prompt text.
            pages: Page objects (unused by this adapter; reserved for future use).
            prompts: Prompt configuration with system prompt and course supplement.
        """
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY is required")
        system = prompts.system
        if prompts.course_supplement:
            system = f"{system}\n\n## コース固有指示\n{prompts.course_supplement}"
        response_json = self._call_api(system, text)
        try:
            return parse_llm_response(response_json)
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            raise LLMError(f"Failed to parse LLM response: {exc}") from exc

    def extract_tour_header(self, excerpt: str) -> TourHeaderData | None:
        """Extract tour header via OpenAI LLM from a rooming list excerpt."""
        if not self.api_key:
            return None
        if not excerpt.strip():
            return None
        system_prompt = (
            "You extract only tour header fields from rooming list text. "
            "Return strict JSON with keys: tour_ref, tour_name, confidence. "
            "tour_ref format must be '<COURSE_CODE> MMDD' such as 'E417Z 1027'."
        )
        user_prompt = (
            "Extract tour_ref and tour_name from the following rooming-list header text. "
            "If unknown, use null. confidence must be between 0 and 1.\n\n"
            f"{excerpt}"
        )
        response_json = self._call_api_with_schema(
            system_prompt, user_prompt, self._tour_header_schema(),
        )
        candidate = json.loads(response_json)
        if not isinstance(candidate, dict):
            return None
        return normalize_tour_header_candidate(candidate)

    @staticmethod
    def _tour_header_schema() -> dict[str, object]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "tour_ref": {"type": ["string", "null"]},
                "tour_name": {"type": ["string", "null"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["tour_ref", "tour_name", "confidence"],
        }

    def _build_payload(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        """Build the OpenAI Responses API request payload."""
        payload: dict[str, object] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_output_tokens": self.max_output_tokens,
            "reasoning": {"effort": "medium"},
        }
        if self._schema:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "ml_items",
                    "strict": True,
                    "schema": self._schema,
                },
            }
        return payload

    def _call_api_with_schema(
        self, system_prompt: str, user_prompt: str, schema: dict[str, object],
    ) -> str:
        """Send request to OpenAI with a specific JSON schema."""
        payload: dict[str, object] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_output_tokens": self.max_output_tokens,
            "reasoning": {"effort": "medium"},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "tour_header",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        data = json.dumps(payload).encode("utf-8")
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(
                self.endpoint,
                data=data,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8")
                return self._extract_output_text(json.loads(body))
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
            ) as exc:
                last_exc = exc
                retryable, retry_after = _is_retryable_error(exc)
                if not retryable or attempt >= self.max_retries:
                    raise LLMError(f"OpenAI API error: {exc}") from exc
                delay = _get_retry_delay(attempt, retry_after=retry_after)
                self._sleep_fn(delay)
        raise LLMError(f"OpenAI API error: {last_exc}") from last_exc  # pragma: no cover

    def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        """Send request to OpenAI with retry on transient errors."""
        payload = self._build_payload(system_prompt, user_prompt)
        data = json.dumps(payload).encode("utf-8")
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(
                self.endpoint,
                data=data,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8")
                return self._extract_output_text(json.loads(body))
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
            ) as exc:
                last_exc = exc
                retryable, retry_after = _is_retryable_error(exc)
                if not retryable or attempt >= self.max_retries:
                    raise LLMError(f"OpenAI API error: {exc}") from exc
                delay = _get_retry_delay(attempt, retry_after=retry_after)
                self._sleep_fn(delay)

        raise LLMError(f"OpenAI API error: {last_exc}") from last_exc  # pragma: no cover

    @staticmethod
    def _extract_output_text(parsed: dict[str, object]) -> str:
        """Extract the output text from an OpenAI Responses API response."""
        output_text = parsed.get("output_text")
        if isinstance(output_text, str):
            return output_text

        output = parsed.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for chunk in content:
                        if isinstance(chunk, dict) and chunk.get("type") == "output_text":
                            t = chunk.get("text")
                            if isinstance(t, str):
                                parts.append(t)
                ot = item.get("output_text")
                if isinstance(ot, str):
                    parts.append(ot)
            if parts:
                return "".join(parts)

        raise LLMError("Failed to extract output text from OpenAI response")
