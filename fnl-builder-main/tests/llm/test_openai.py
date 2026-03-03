"""Tests for OpenAI adapter."""
from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from fnl_builder.llm.adapter import PromptConfig
from fnl_builder.llm.openai import (
    OpenAIAdapter,
    _get_retry_delay,
    _is_retryable_error,
)
from fnl_builder.shared.errors import LLMError


def _make_prompts() -> PromptConfig:
    return PromptConfig(
        system="You are a system.",
        extract_base="Extract {{PAGES_TEXT}}",
        course_supplement="Course supplement",
    )


def _make_api_response(items: list[dict[str, Any]]) -> str:
    """Build a fake OpenAI Responses API JSON response."""
    return json.dumps({"output_text": json.dumps({"items": items})})


def _valid_item() -> dict[str, Any]:
    return {
        "category": "medical_health",
        "phase": "on_tour",
        "summary": "Test",
        "handoff_text": "Handle it",
        "explicitness": "explicit",
        "urgency": "high",
        "confidence": 0.9,
        "severity": "warning",
        "caution_reason": "",
        "evidence_match": True,
        "evidence": {"page": 1, "quote": "test quote"},
    }


class TestProtocolConformance:
    def test_has_extract_remarks(self) -> None:
        adapter = OpenAIAdapter(api_key="test-key")
        assert hasattr(adapter, "extract_remarks")
        assert callable(adapter.extract_remarks)

class TestPostInit:
    def test_api_key_from_env(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            adapter = OpenAIAdapter()
            assert adapter.api_key == "env-key"

    def test_model_from_env(self) -> None:
        with patch.dict("os.environ", {"OPENAI_MODEL": "gpt-custom"}):
            adapter = OpenAIAdapter(api_key="k")
            assert adapter.model == "gpt-custom"

    def test_explicit_overrides_env(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env", "OPENAI_MODEL": "env-model"}):
            adapter = OpenAIAdapter(api_key="explicit", model="explicit-model")
            assert adapter.api_key == "explicit"
            assert adapter.model == "explicit-model"

    def test_default_model(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            adapter = OpenAIAdapter(api_key="k")
            assert adapter.model == "gpt-5.2"


class TestBuildPayload:
    def test_basic_structure(self) -> None:
        adapter = OpenAIAdapter(api_key="k", model="gpt-test")
        payload = adapter._build_payload("sys", "usr")
        assert payload["model"] == "gpt-test"
        assert isinstance(payload["input"], list)
        messages = payload["input"]
        assert len(messages) == 2  # type: ignore[arg-type]
        assert messages[0] == {"role": "system", "content": "sys"}  # type: ignore[index]
        assert messages[1] == {"role": "user", "content": "usr"}  # type: ignore[index]
        assert payload["reasoning"] == {"effort": "medium"}
        assert payload["max_output_tokens"] == 16384

    def test_schema_included(self) -> None:
        adapter = OpenAIAdapter(api_key="k", _schema={"type": "object"})
        payload = adapter._build_payload("sys", "usr")
        assert "text" in payload
        text_config = payload["text"]
        assert isinstance(text_config, dict)
        fmt = text_config["format"]  # type: ignore[index]
        assert fmt["type"] == "json_schema"  # type: ignore[index]
        assert fmt["strict"] is True  # type: ignore[index]

    def test_no_schema(self) -> None:
        adapter = OpenAIAdapter.__new__(OpenAIAdapter)
        adapter.api_key = "k"
        adapter.model = "gpt-test"
        adapter.endpoint = "http://test"
        adapter.max_retries = 0
        adapter.max_output_tokens = 16384
        adapter.timeout = 600
        adapter._schema = None
        adapter._sleep_fn = lambda _: None
        payload = adapter._build_payload("sys", "usr")
        assert "text" not in payload


class TestExtractOutputText:
    def test_top_level_output_text(self) -> None:
        result = OpenAIAdapter._extract_output_text({"output_text": "hello"})
        assert result == "hello"

    def test_nested_content_blocks(self) -> None:
        resp = {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": "part1"},
                        {"type": "output_text", "text": "part2"},
                    ]
                }
            ]
        }
        result = OpenAIAdapter._extract_output_text(resp)
        assert result == "part1part2"

    def test_nested_output_text_field(self) -> None:
        resp = {"output": [{"output_text": "fallback"}]}
        result = OpenAIAdapter._extract_output_text(resp)
        assert result == "fallback"

    def test_no_output_raises(self) -> None:
        with pytest.raises(LLMError, match="Failed to extract"):
            OpenAIAdapter._extract_output_text({})

    def test_empty_output_list_raises(self) -> None:
        with pytest.raises(LLMError, match="Failed to extract"):
            OpenAIAdapter._extract_output_text({"output": []})


class TestExtractRemarks:
    def test_no_api_key_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            adapter = OpenAIAdapter(api_key="")
            with pytest.raises(LLMError, match="OPENAI_API_KEY"):
                adapter.extract_remarks("text", [], _make_prompts())

    def test_success_with_mock_api(self) -> None:
        adapter = OpenAIAdapter(api_key="test-key", _schema=None)
        response_body = _make_api_response([_valid_item()])

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = response_body.encode("utf-8")
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            items = adapter.extract_remarks("user text", [], _make_prompts())
            assert len(items) == 1
            assert items[0].summary == "Test"

    def test_malformed_response_raises_llm_error(self) -> None:
        adapter = OpenAIAdapter(api_key="test-key", _schema=None)
        # API returns valid HTTP but malformed JSON content
        bad_response = json.dumps({"output_text": "not valid json {"})

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = bad_response.encode("utf-8")
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            with pytest.raises(LLMError, match="Failed to parse"):
                adapter.extract_remarks("text", [], _make_prompts())

    def test_course_supplement_appended(self) -> None:
        adapter = OpenAIAdapter(api_key="test-key", _schema=None)
        response_body = _make_api_response([_valid_item()])

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = response_body.encode("utf-8")
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            prompts = _make_prompts()
            adapter.extract_remarks("text", [], prompts)

            call_args = mock_urlopen.call_args
            req = call_args[0][0]
            sent_data = json.loads(req.data.decode("utf-8"))
            system_msg = sent_data["input"][0]["content"]
            assert "Course supplement" in system_msg


class TestRetryLogic:
    def test_retry_on_429(self) -> None:
        adapter = OpenAIAdapter(
            api_key="test-key",
            max_retries=1,
            _schema=None,
            _sleep_fn=lambda _: None,
        )
        response_body = _make_api_response([_valid_item()])

        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise urllib.error.HTTPError(
                    "url", 429, "Too Many Requests", {}, BytesIO(b"")  # type: ignore[arg-type]
                )
            mock_resp = MagicMock()
            mock_resp.read.return_value = response_body.encode("utf-8")
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=side_effect):
            items = adapter.extract_remarks("text", [], _make_prompts())
            assert len(items) == 1
            assert call_count == 2

    def test_no_retry_on_401(self) -> None:
        adapter = OpenAIAdapter(
            api_key="test-key",
            max_retries=2,
            _schema=None,
            _sleep_fn=lambda _: None,
        )

        def side_effect(*args: Any, **kwargs: Any) -> Any:
            raise urllib.error.HTTPError(
                "url", 401, "Unauthorized", {}, BytesIO(b"")  # type: ignore[arg-type]
            )

        with patch("urllib.request.urlopen", side_effect=side_effect):
            with pytest.raises(LLMError, match="OpenAI API error"):
                adapter.extract_remarks("text", [], _make_prompts())

    def test_max_retries_exhausted(self) -> None:
        adapter = OpenAIAdapter(
            api_key="test-key",
            max_retries=2,
            _schema=None,
            _sleep_fn=lambda _: None,
        )
        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            raise urllib.error.HTTPError(
                "url", 500, "Server Error", {}, BytesIO(b"")  # type: ignore[arg-type]
            )

        with patch("urllib.request.urlopen", side_effect=side_effect):
            with pytest.raises(LLMError):
                adapter.extract_remarks("text", [], _make_prompts())
            assert call_count == 3  # 1 initial + 2 retries


class TestRetryDelay:
    def test_first_attempt(self) -> None:
        delay = _get_retry_delay(0)
        assert 1.0 <= delay <= 1.25  # base * (2^0) + jitter

    def test_second_attempt(self) -> None:
        delay = _get_retry_delay(1)
        assert 2.0 <= delay <= 2.5

    def test_capped_at_max(self) -> None:
        delay = _get_retry_delay(100, max_delay=30.0)
        assert delay <= 30.0 * 1.25

    def test_retry_after_header(self) -> None:
        delay = _get_retry_delay(0, retry_after=5.0)
        assert delay == 5.0

    def test_retry_after_capped(self) -> None:
        delay = _get_retry_delay(0, max_delay=3.0, retry_after=10.0)
        assert delay == 3.0


class TestIsRetryableError:
    def test_http_429(self) -> None:
        exc = urllib.error.HTTPError(
            "url", 429, "Rate Limited", {}, BytesIO(b"")  # type: ignore[arg-type]
        )
        retryable, _ = _is_retryable_error(exc)
        assert retryable is True

    def test_http_500(self) -> None:
        exc = urllib.error.HTTPError(
            "url", 500, "Server Error", {}, BytesIO(b"")  # type: ignore[arg-type]
        )
        retryable, _ = _is_retryable_error(exc)
        assert retryable is True

    def test_http_401_not_retryable(self) -> None:
        exc = urllib.error.HTTPError(
            "url", 401, "Unauthorized", {}, BytesIO(b"")  # type: ignore[arg-type]
        )
        retryable, _ = _is_retryable_error(exc)
        assert retryable is False

    def test_url_error_retryable(self) -> None:
        exc = urllib.error.URLError("connection refused")
        retryable, _ = _is_retryable_error(exc)
        assert retryable is True

    def test_timeout_retryable(self) -> None:
        exc = TimeoutError("timed out")
        retryable, _ = _is_retryable_error(exc)
        assert retryable is True

    def test_generic_not_retryable(self) -> None:
        exc = ValueError("bad value")
        retryable, _ = _is_retryable_error(exc)
        assert retryable is False
