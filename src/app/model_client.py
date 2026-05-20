from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from app.loaders import ModelProfile
from app.messages import is_chat_role


Message = dict[str, str]
Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, str]]
StreamTransport = Callable[[str, dict[str, str], bytes, float], Iterable[str]]


class ModelClientError(Exception):
    """Base error for model client failures."""


class MissingApiKeyError(ModelClientError):
    """Raised when the configured API key environment variable is unavailable."""


class MissingEndpointError(ModelClientError):
    """Raised when the configured model endpoint is unavailable."""


class ModelHTTPError(ModelClientError):
    """Raised when the model endpoint returns an error status."""


class ModelResponseError(ModelClientError):
    """Raised when the model endpoint returns an invalid response."""


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    raw: dict[str, Any]


class OpenAICompatibleClient:
    def __init__(
        self,
        env: dict[str, str] | None = None,
        transport: Transport | None = None,
        stream_transport: StreamTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.env = env if env is not None else os.environ
        self.transport = transport or _urllib_transport
        self.stream_transport = stream_transport or _urllib_stream_transport
        self.sleep = sleep

    def resolve_api_key(self, profile: ModelProfile | dict[str, Any]) -> str:
        data = _profile_data(profile)
        env_name = data.get("api_key_env")
        if not isinstance(env_name, str) or not env_name.strip():
            raise MissingApiKeyError("Profile does not define api_key_env")

        api_key = self.env.get(env_name)
        if not api_key:
            raise MissingApiKeyError(f"API key environment variable is not set: {env_name}")
        return api_key

    def resolve_endpoint(self, profile: ModelProfile | dict[str, Any]) -> str:
        data = _profile_data(profile)
        env_name = data.get("endpoint_env")
        if isinstance(env_name, str) and env_name.strip():
            endpoint = self.env.get(env_name)
            if not endpoint:
                raise MissingEndpointError(f"Endpoint environment variable is not set: {env_name}")
            return endpoint
        return _require_string(data, "endpoint")

    def build_chat_payload(self, profile: ModelProfile | dict[str, Any], messages: list[Message]) -> dict[str, Any]:
        data = _profile_data(profile)
        _validate_messages(messages)

        payload: dict[str, Any] = {
            "model": _require_string(data, "model"),
            "messages": messages,
        }
        for optional in ("temperature", "top_p", "top_k", "max_tokens", "stop", "frequency_penalty", "presence_penalty", "repetition_penalty"):
            if optional in data:
                payload[optional] = data[optional]
        if data.get("response_format") is not None:
            payload["response_format"] = data["response_format"]
        if isinstance(data.get("reasoning_effort"), str) and data["reasoning_effort"]:
            payload["reasoning_effort"] = data["reasoning_effort"]
        return payload

    def create_chat_completion(self, profile: ModelProfile | dict[str, Any], messages: list[Message]) -> ChatCompletionResult:
        data = _profile_data(profile)
        api_key = self.resolve_api_key(data)
        payload = self.build_chat_payload(data, messages)
        endpoint = _chat_completions_url(self.resolve_endpoint(data))
        timeout = _timeout_seconds(data)
        retry_count = _retry_count(data)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        last_error: ModelClientError | None = None
        for attempt in range(retry_count + 1):
            try:
                status, response_text = self.transport(endpoint, headers, body, timeout)
                if status < 200 or status >= 300:
                    raise ModelHTTPError(f"Model endpoint returned HTTP {status}")
                return _parse_chat_completion_response(response_text)
            except ModelHTTPError as exc:
                last_error = exc
                if status < 500 or attempt >= retry_count:
                    raise exc
            except (ModelResponseError, ModelClientError):
                raise
            except Exception as exc:
                last_error = ModelClientError(f"Model request failed: {type(exc).__name__}")
                if attempt >= retry_count:
                    raise last_error from exc
            self.sleep(0)

        raise last_error or ModelClientError("Model request failed")

    def create_chat_completion_stream(
        self, profile: ModelProfile | dict[str, Any], messages: list[Message]
    ) -> Iterable[str]:
        data = _profile_data(profile)
        api_key = self.resolve_api_key(data)
        payload = self.build_chat_payload(data, messages)
        payload["stream"] = True
        endpoint = _chat_completions_url(self.resolve_endpoint(data))
        timeout = _timeout_seconds(data)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        try:
            yield from _parse_chat_completion_stream(self.stream_transport(endpoint, headers, body, timeout))
        except ModelClientError:
            raise
        except Exception as exc:
            raise ModelClientError(f"Model stream request failed: {type(exc).__name__}") from exc


def _profile_data(profile: ModelProfile | dict[str, Any]) -> dict[str, Any]:
    if isinstance(profile, ModelProfile):
        return profile.data
    return profile


def _validate_messages(messages: list[Message]) -> None:
    if not isinstance(messages, list) or not messages:
        raise ModelClientError("messages must be a non-empty list")
    for message in messages:
        if not isinstance(message, dict):
            raise ModelClientError("each message must be an object")
        role = message.get("role")
        content = message.get("content")
        if not is_chat_role(role):
            raise ModelClientError("message role is invalid")
        if not isinstance(content, str):
            raise ModelClientError("message content must be a string")


def _require_string(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ModelClientError(f"Profile field is missing or invalid: {field}")
    return value


def _timeout_seconds(data: dict[str, Any]) -> float:
    value = data.get("timeout_seconds", 60)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ModelClientError("timeout_seconds must be a positive number")
    return float(value)


def _retry_count(data: dict[str, Any]) -> int:
    value = data.get("retry_count", 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ModelClientError("retry_count must be a non-negative integer")
    return value


def _chat_completions_url(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _parse_chat_completion_response(response_text: str) -> ChatCompletionResult:
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ModelResponseError("Model response is not valid JSON") from exc

    if not isinstance(data, dict):
        raise ModelResponseError("Model response root must be an object")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ModelResponseError("Model response does not contain choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ModelResponseError("Model response choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ModelResponseError("Model response choice does not contain a message")
    content = message.get("content")
    if not isinstance(content, str):
        raise ModelResponseError("Model response message content must be a string")
    reasoning = message.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        content = f"<reasoning>{reasoning.strip()}</reasoning>\n{content}"
    return ChatCompletionResult(content=content, raw=data)


def _parse_chat_completion_stream(lines: Iterable[str]) -> Iterable[str]:
    in_reasoning = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(":"):
            continue
        if not stripped.startswith("data:"):
            continue
        data_text = stripped.removeprefix("data:").strip()
        if data_text == "[DONE]":
            break
        try:
            data = json.loads(data_text)
        except json.JSONDecodeError as exc:
            raise ModelResponseError("Model stream chunk is not valid JSON") from exc
        if not isinstance(data, dict):
            raise ModelResponseError("Model stream chunk root must be an object")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            continue
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            continue
        finish_reason = first_choice.get("finish_reason")
        if finish_reason is not None:
            break
        delta = first_choice.get("delta")
        if isinstance(delta, dict):
            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
            content = delta.get("content")
            if isinstance(reasoning, str) and reasoning:
                if not in_reasoning:
                    yield "<reasoning>"
                    in_reasoning = True
                yield reasoning
            if isinstance(content, str) and content:
                if in_reasoning:
                    yield "</reasoning>\n"
                    in_reasoning = False
                yield content
            continue
        message = first_choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content:
                if in_reasoning:
                    yield "</reasoning>\n"
                    in_reasoning = False
                yield content
    if in_reasoning:
        yield "</reasoning>\n"


def _urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _urllib_stream_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> Iterable[str]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status < 200 or status >= 300:
                raise ModelHTTPError(f"Model endpoint returned HTTP {status}")
            for raw_line in response:
                yield raw_line.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ModelHTTPError(f"Model endpoint returned HTTP {exc.code}: {detail}") from exc
