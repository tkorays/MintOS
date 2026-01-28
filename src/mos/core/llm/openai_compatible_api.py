"""OpenAI-compatible chat completions client.

Thin, dependency-light wrapper around any HTTP endpoint that speaks the
``/v1/chat/completions`` shape — OpenAI, DeepSeek, Moonshot, OpenRouter,
local Ollama (``/v1/chat/completions``), vLLM, etc.

Design notes:

* **Sync first.** The Lua source this is ported from used Hammerspoon's
  ``hs.http.asyncPost``; Python's standard idiom is synchronous, and
  async wrapping (``asyncio.to_thread``) is trivial when needed.
* **Exceptions over callbacks.** The Lua API returned ``(value, err)``
  tuples via callbacks; Python raises :class:`OpenAICompatibleError`
  instead and lets callers ``try/except``. The structured-content
  parser still degrades to a typed error on failure.
* **Pluggable parsers.** ``request_builder`` / ``response_parser`` keep
  per-vendor quirks out of the core — e.g. Azure wants
  ``api-version`` in the URL, Anthropic-via-OpenRouter wants
  ``transforms``, etc.
* **Robust content parsing.** Model output frequently wraps JSON in a
  triple-backtick `json` fence, sometimes inside surrounding prose.
  :func:`decode_structured_content` tries (in order) the fenced body,
  the first balanced JSON object/array in the string, then the raw
  content. All candidates are deduplicated.

Public surface:

* :class:`ChatOptions` — request payload.
* :class:`ChatResult` — typed result carrying both the parsed payload
  and the raw response dict.
* :class:`OpenAICompatibleClient` — the HTTP client.
* Module-level helpers: :func:`extract_text_from_content`,
  :func:`decode_structured_content`, :func:`safe_json_decode`,
  :func:`strip_code_fence`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import requests
from loguru import logger

RequestBuilder = Callable[[dict[str, Any]], dict[str, Any]]
"""Hook called with the chat-completions payload, returning the actual
request body to send. Use to adapt to vendor-specific request shapes."""

ResponseParser = Callable[[dict[str, Any]], dict[str, Any]]
"""Hook called with the decoded JSON response. Return the dict you want
exposed as ``ChatResult.raw``. Use to normalise vendor responses."""

DEFAULT_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_TIMEOUT = 25
PLACEHOLDER_KEY = "YOUR_API_KEY"


class OpenAICompatibleError(RuntimeError):
    """Raised for any client / parse failure.

    Network errors, non-2xx responses, JSON decode failures, and
    structured-content parse failures all surface here so callers can
    catch them uniformly.
    """


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


@dataclass
class ChatOptions:
    """Per-request overrides for a chat-completions call.

    Attributes default to ``None`` so the client's own ``model`` /
    ``temperature`` etc. flow through. Pass an explicit value here to
    override for a single call.
    """

    messages: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    response_format: dict[str, Any] | None = None
    extra_body: dict[str, Any] = field(default_factory=dict)
    """Vendor-specific fields merged into the payload after the standard
    ones (e.g. ``tools``, ``stream``). Keys here win on collision."""


@dataclass
class ChatResult:
    """Parsed assistant payload plus the raw HTTP response.

    Attributes:
        payload: The ``choices[0].message.content`` — text for
            :meth:`OpenAICompatibleClient.chat_text`, parsed JSON for
            :meth:`OpenAICompatibleClient.chat_json`.
        raw: The full decoded response dict, in case callers need
            ``usage`` / ``model`` / vendor-specific fields.
    """

    payload: Any
    raw: dict[str, Any]


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class OpenAICompatibleClient:
    """Stateless HTTP client for OpenAI-compatible chat completions.

    A single instance can serve many calls — ``requests.Session``
    pools connections. Configure once at startup (endpoint / key /
    model), then call :meth:`chat_text` / :meth:`chat_json` per request.

    Example:
        >>> client = OpenAICompatibleClient(api_key="sk-...", model="gpt-4o-mini")
        >>> text = client.chat_text(ChatOptions(messages=[
        ...     {"role": "user", "content": "Say hi in one word."}
        ... ]))
    """

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        api_key: str = "",
        model: str = "",
        extra_headers: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
        request_builder: RequestBuilder | None = None,
        response_parser: ResponseParser | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.extra_headers = dict(extra_headers or {})
        self.timeout = timeout
        self.request_builder = request_builder
        self.response_parser = response_parser
        self._session = session or requests.Session()

    # -- Headers / payload -------------------------------------------------

    def build_headers(self) -> dict[str, str]:
        """Compose request headers, injecting ``Authorization`` if a real key is set.

        A blank key or the ``PLACEHOLDER_KEY`` sentinel is treated as
        "no key" — useful for local servers that don't require auth.
        """
        headers = dict(self.extra_headers)
        if self.api_key and self.api_key != PLACEHOLDER_KEY:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.setdefault("Content-Type", "application/json")
        return headers

    def build_chat_payload(self, options: ChatOptions) -> dict[str, Any]:
        """Materialise the JSON body for a chat-completions request."""
        payload: dict[str, Any] = {
            "model": options.model or self.model,
            "messages": options.messages,
        }
        if options.temperature is not None:
            payload["temperature"] = options.temperature
        if options.top_p is not None:
            payload["top_p"] = options.top_p
        if options.max_tokens is not None:
            payload["max_tokens"] = options.max_tokens
        if options.response_format is not None:
            payload["response_format"] = options.response_format
        payload.update(options.extra_body)
        return payload

    # -- Transport ---------------------------------------------------------

    def send(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """POST ``payload`` to the endpoint and return the decoded JSON response.

        Raises:
            OpenAICompatibleError: on network failure, non-2xx status,
                or non-JSON response body.
        """
        body = payload
        if self.request_builder is not None:
            body = self.request_builder(dict(payload))

        try:
            response = self._session.post(
                self.endpoint,
                json=body,
                headers=self.build_headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise OpenAICompatibleError(
                f"OpenAI-compatible request failed: {exc}"
            ) from exc

        if not 200 <= response.status_code < 300:
            preview = (response.text or "").strip()[:400]
            raise OpenAICompatibleError(
                f"OpenAI-compatible request failed ({response.status_code}): {preview}"
            )

        try:
            decoded = response.json()
        except ValueError as exc:
            logger.error(
                "Failed to decode OpenAI-compatible response. status={} body={}",
                response.status_code,
                (response.text or "")[:400],
            )
            raise OpenAICompatibleError(
                f"Response body is not valid JSON: {exc}"
            ) from exc

        if not isinstance(decoded, dict):
            raise OpenAICompatibleError(
                f"Decoded response is not an object: {type(decoded).__name__}"
            )

        return decoded

    # -- High-level helpers ------------------------------------------------

    def chat(self, options: ChatOptions) -> ChatResult:
        """Send a chat-completions request and return the raw decoded response.

        Most callers want :meth:`chat_text` or :meth:`chat_json` instead.
        """
        payload = self.build_chat_payload(options)
        decoded = self.send(payload)
        parsed = self.response_parser(decoded) if self.response_parser else decoded
        return ChatResult(payload=parsed, raw=decoded)

    def chat_text(self, options: ChatOptions) -> str:
        """Send a chat request and return the assistant's text content.

        Handles both string content (``"hello"``) and the modern list-of-
        parts shape returned by some vendors / vision models.
        """
        result = self.chat(options)
        text, err = extract_text_from_content(self._assistant_content(result))
        if err:
            raise OpenAICompatibleError(err)
        assert text is not None  # err is None ⇒ text is not None
        return text

    def chat_json(self, options: ChatOptions) -> Any:
        """Send a chat request and return JSON parsed from the assistant content.

        ``ChatOptions.response_format={"type": "json_object"}`` is
        recommended to nudge the model; this method still tolerates
        code-fenced or prose-wrapped JSON output.
        """
        result = self.chat(options)
        content = self._assistant_content(result)
        # If the parser swapped in a non-OpenAI shape, fall back to the
        # whole payload — response_parser may already give us structured data.
        if not content:
            return result.payload
        structured, err = decode_structured_content(content)
        if err:
            raise OpenAICompatibleError(err)
        return structured

    # -- Internals ---------------------------------------------------------

    @staticmethod
    def _assistant_content(result: ChatResult) -> Any:
        """Pull ``choices[0].message.content`` out of a decoded response.

        Returns ``None`` when the shape is missing — vision models and
        tool-calling responses can leave ``content`` empty.
        """
        try:
            return result.payload["choices"][0]["message"].get("content")
        except (KeyError, IndexError, TypeError, AttributeError):
            return None


# ---------------------------------------------------------------------------
# Content-parsing helpers
# ---------------------------------------------------------------------------


def safe_json_decode(text: str, label: str = "json") -> Any:
    """Decode ``text`` as JSON, with a friendly error.

    Unlike :func:`json.loads`, this rejects empty strings and non-JSON
    prefixes explicitly so callers get actionable error messages.

    Raises:
        OpenAICompatibleError: when the input is not JSON.
    """
    if not isinstance(text, str):
        raise OpenAICompatibleError(
            f"{label} is not a string (got {type(text).__name__})"
        )

    normalized = text.strip()
    if not normalized:
        raise OpenAICompatibleError(f"{label} is empty")
    if normalized[0] not in "{[":
        raise OpenAICompatibleError(
            f"{label} does not look like JSON: {preview(normalized, 220)}"
        )

    try:
        decoded = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise OpenAICompatibleError(
            f"Failed to decode {label}: {exc}"
        ) from exc

    if not isinstance(decoded, (dict, list)):
        raise OpenAICompatibleError(f"Decoded {label} is not an object/array")
    return decoded


def strip_code_fence(content: str) -> str:
    """Strip a single triple-backtick `json` (or plain) fence.

    No-op for non-string input. Only the outer fence is removed; inner
    fences are left intact.
    """
    if not isinstance(content, str):
        return content
    content = content.strip()
    content = re.sub(r"^```json\s*", "", content)
    content = re.sub(r"^```\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    return content.strip()


def extract_text_from_content(content: Any) -> tuple[str | None, str | None]:
    """Flatten OpenAI-style assistant ``content`` to a single string.

    Modern APIs return ``content`` as either a string or a list of
    parts. Parts can carry text under ``text``, ``content``, or
    ``type="text", value=...`` depending on the vendor. Returns
    ``(text, None)`` on success or ``(None, error)`` on failure.

    ``<think>...</think>`` blocks (emitted by reasoning models such as
    DeepSeek-R1, MiniMax-M3, Qwen-QwQ, etc.) are stripped first so
    they don't contaminate downstream JSON extraction — a model that
    thinks aloud before answering will otherwise leak curly braces
    from its prose into the parse candidates.
    """
    if isinstance(content, str):
        return _strip_think_blocks(content), None

    if not isinstance(content, list):
        return None, f"message.content has unsupported type: {type(content).__name__}"

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            value = item.get("text")
            if isinstance(value, str):
                parts.append(value)
                continue
            value = item.get("content")
            if isinstance(value, str):
                parts.append(value)
                continue
            if item.get("type") == "text" and isinstance(item.get("value"), str):
                parts.append(item["value"])

    merged = "\n".join(parts).strip()
    if not merged:
        return None, "message.content list does not contain any readable text"
    return _strip_think_blocks(merged), None


def decode_structured_content(content: Any) -> tuple[Any | None, str | None]:
    """Best-effort JSON extraction from assistant content.

    Tries three candidates in order — the code-fence-stripped body,
    the first fenced block, and the first balanced JSON object/array —
    and returns the first that parses. All candidates are
    deduplicated so a string that equals itself under different
    preprocessing strategies isn't tried twice.

    Returns ``(value, None)`` on success or ``(None, error)`` on
    failure (the error includes a content preview and per-candidate
    parse errors for debugging).
    """
    text, err = extract_text_from_content(content)
    if err:
        return None, err

    candidates: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        value = value.strip()
        if value and value not in seen:
            seen.add(value)
            candidates.append(value)

    add(strip_code_fence(text))
    fenced = _extract_first_fenced_block(text)
    if fenced:
        add(fenced)
    balanced = _extract_balanced_json(text)
    if balanced:
        add(balanced)

    errors: list[str] = []
    for candidate in candidates:
        try:
            return safe_json_decode(candidate, "model content"), None
        except OpenAICompatibleError as exc:
            errors.append(str(exc))

    return None, (
        f"Unable to parse JSON from model response. "
        f"Content preview: {preview(text, 220)} | Attempts: {' || '.join(errors)}"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def preview(text: str, limit: int = 160) -> str:
    """One-line, whitespace-collapsed preview of ``text``.

    Used in error messages where newlines and long output would
    clutter logs. Adds an ellipsis when truncated.
    """
    limit = max(1, limit)
    flat = re.sub(r"\s+", " ", (text or "").strip())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"


def _strip_think_blocks(content: str) -> str:
    """Remove ``<think>...</think>`` blocks (and bare ``<think>...``).

    Reasoning models routinely emit these inline with their answer.
    Stripping them is safe for non-reasoning models (no-op when absent)
    and prevents the inner prose from polluting JSON extraction.
    """
    if not isinstance(content, str):
        return content
    return re.sub(r"<think[^>]*>.*?</think>", "", content, flags=re.DOTALL).strip()


def _extract_first_fenced_block(content: str) -> str | None:
    """Return the body of the first triple-backtick block (preferring `json`)."""
    if not isinstance(content, str):
        return None

    json_block = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
    if json_block and json_block.group(1).strip():
        return json_block.group(1).strip()

    plain_block = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
    if plain_block and plain_block.group(1).strip():
        return plain_block.group(1).strip()

    return None


def _extract_balanced_json(content: str) -> str | None:
    """Return the first balanced ``{...}`` or ``[...]`` substring.

    Respects string boundaries and escape sequences so braces inside
    JSON strings don't break the depth count. Used as a last-resort
    fallback when the model emits JSON embedded in prose.
    """
    if not isinstance(content, str):
        return None

    match = re.search(r"[\{\[]", content)
    if not match:
        return None

    start = match.start()
    opener = content[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escaped = False

    for i, ch in enumerate(content[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return content[start : i + 1]
    return None
