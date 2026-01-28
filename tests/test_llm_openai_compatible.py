"""Live smoke tests against an OpenAI-compatible endpoint.

Three flows are exercised, each mirroring a real usage pattern from
``~/.hammerspoon/im_reply_assistant.lua``:

1. :func:`test_chat_text_smoke` — bare ``client.chat_text`` with a simple
   user prompt.
2. :func:`test_chat_json_smoke` — ``client.chat_json`` with
   ``response_format=json_object``; verifies code-fence stripping and
   balanced-JSON fallback work against real model output.
3. :func:`test_review_and_polish_smoke` — the full draft-rewrite workflow
   used by ``im_reply_assistant.lua``: build payload, send, parse the
   structured reply into the canonical ``{risk_check, missing_info,
   polished, variants}`` shape.

Configuration is read from environment variables so the API key is
never committed:

* ``OPENAI_COMPAT_API_KEY`` — required (tests skip if unset)
* ``OPENAI_COMPAT_ENDPOINT`` — defaults to the minimaxi endpoint
  mirroring ``im_reply_assistant.lua``
* ``OPENAI_COMPAT_MODEL`` — defaults to ``MiniMax-M3``

Gates (both required to actually hit the network):

* ``RUN_LLM_NETWORK_TESTS=1`` — opt-in flag
* ``OPENAI_COMPAT_API_KEY`` set — otherwise skip with a hint

Run with::

    export OPENAI_COMPAT_API_KEY="sk-..."
    RUN_LLM_NETWORK_TESTS=1 PYTHONPATH=src pytest tests/test_llm_openai_compatible.py -v -s
"""

from __future__ import annotations

import os
import textwrap
import time
from dataclasses import dataclass

import pytest

from mos.core.llm.openai_compatible_api import (
    ChatOptions,
    ChatResult,
    OpenAICompatibleClient,
    OpenAICompatibleError,
    decode_structured_content,
)


# ---------------------------------------------------------------------------
# Config — env-driven, defaults mirror ~/.hammerspoon/im_reply_assistant.lua
# ---------------------------------------------------------------------------

ENV_ENDPOINT = "OPENAI_COMPAT_ENDPOINT"
ENV_MODEL = "OPENAI_COMPAT_MODEL"
ENV_API_KEY = "OPENAI_COMPAT_API_KEY"

DEFAULT_ENDPOINT = "https://api.minimaxi.com/v1/chat/completions"
DEFAULT_MODEL = "MiniMax-M3"


def _config() -> tuple[str, str, str]:
    """Read ``(endpoint, model, api_key)`` from the environment.

    Endpoint and model fall back to the minimaxi defaults so the test
    works against the same provider as ``im_reply_assistant.lua`` with
    only the key set. The key has no default — missing key skips the
    test rather than sending an unauthenticated request.
    """
    endpoint = os.environ.get(ENV_ENDPOINT, DEFAULT_ENDPOINT)
    model = os.environ.get(ENV_MODEL, DEFAULT_MODEL)
    api_key = os.environ.get(ENV_API_KEY, "")
    return endpoint, model, api_key

REVIEW_SYSTEM_PROMPT = textwrap.dedent(
    """
    You are a pre-send assistant for instant messaging replies.
    The user message you receive is NOT an incoming message that needs a reply.
    It is my existing draft reply that I have already typed in the current input
    box and want you to rewrite.
    Do not answer the draft. Do not continue the conversation. Do not act like a
    chat assistant replying to it.
    Treat the input as DRAFT_REPLY_TO_REWRITE.
    Return JSON only.
    Do four things in order: validate risk, find missing information, polish the
    reply, and provide variants.
    Keep the original intent unless it is clearly risky or unclear.
    Do not invent facts. If key information is missing, keep uncertainty explicit.
    JSON schema:
    {"risk_check":["..."],"missing_info":["..."],"polished":"...","variants":{"concise":"...","polite":"...","direct":"..."}}
    """
).strip()


def _client() -> OpenAICompatibleClient:
    """Build a client matching the Lua ``createOpenAIClient`` config."""
    endpoint, model, api_key = _config()
    return OpenAICompatibleClient(
        endpoint=endpoint,
        api_key=api_key,
        model=model,
        extra_headers={"Content-Type": "application/json"},
        timeout=25,
    )


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

_NEEDS_NETWORK_FLAG = pytest.mark.skipif(
    os.environ.get("RUN_LLM_NETWORK_TESTS") != "1",
    reason="set RUN_LLM_NETWORK_TESTS=1 to run live LLM smoke tests",
)

_NEEDS_API_KEY = pytest.mark.skipif(
    not os.environ.get(ENV_API_KEY),
    reason=(
        f"set {ENV_API_KEY} in the environment to authenticate "
        f"(optionally also {ENV_ENDPOINT} / {ENV_MODEL})"
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class ParsedReply:
    """Mirror of the Lua ``normalizeResult`` output shape."""

    risk_check: list[str]
    missing_info: list[str]
    polished: str
    variants: dict[str, str]


def _normalize_result(result: ChatResult) -> ParsedReply:
    """Replicate ``im_reply_assistant.lua``'s ``normalizeResult`` in Python.

    Pulls the assistant content, parses the structured JSON, then maps
    it to the canonical reply shape. Mirrors the Lua code line-for-line
    so a regression in either side surfaces here.
    """
    try:
        message = result.raw["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenAICompatibleError(
            f"LLM response missing choices[0].message: {exc}"
        ) from exc

    structured, err = decode_structured_content(message.get("content"))
    if err:
        raise OpenAICompatibleError(err)

    polished = structured.get("polished") or structured.get("recommended") or structured.get("final_reply")
    if not isinstance(polished, str) or not polished.strip():
        raise OpenAICompatibleError("LLM response missing polished text")

    raw_variants = structured.get("variants") or {}
    variants = {
        key: raw_variants.get(key) for key in ("concise", "polite", "direct")
    }

    return ParsedReply(
        risk_check=list(structured.get("risk_check") or []),
        missing_info=list(structured.get("missing_info") or []),
        polished=polished,
        variants={k: v for k, v in variants.items() if isinstance(v, str)},
    )


def _usage_summary(result: ChatResult) -> str:
    """One-line usage printout from the raw response."""
    usage = result.raw.get("usage") or {}
    return (
        f"prompt={usage.get('prompt_tokens')} "
        f"completion={usage.get('completion_tokens')} "
        f"total={usage.get('total_tokens')}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@_NEEDS_NETWORK_FLAG
@_NEEDS_API_KEY
def test_chat_text_smoke():
    """Plain chat_text round-trip — verify transport and basic decoding."""
    client = _client()
    opts = ChatOptions(
        messages=[
            {
                "role": "user",
                "content": "Reply with exactly one short sentence greeting the world.",
            }
        ],
        temperature=0.2,
        max_tokens=64,
    )

    started = time.perf_counter()
    text = client.chat_text(opts)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert isinstance(text, str) and text.strip(), f"empty reply: {text!r}"
    print(f"\n[chat_text] {elapsed_ms:.0f}ms | reply={text!r}")
    print(f"[chat_text] usage: {_usage_summary(client.chat(opts))}")


@_NEEDS_NETWORK_FLAG
@_NEEDS_API_KEY
def test_chat_json_smoke():
    """chat_json with response_format=json_object — verify structured parse.

    The model may still wrap output in a json fence; the parser must
    strip it and return the dict directly.
    """
    client = _client()
    opts = ChatOptions(
        messages=[
            {
                "role": "user",
                "content": (
                    'Return JSON only with shape {"city": "...", "country": "..."} '
                    'for the capital of France.'
                ),
            }
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
        max_tokens=128,
    )

    started = time.perf_counter()
    parsed = client.chat_json(opts)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert isinstance(parsed, dict), f"expected dict, got {type(parsed).__name__}: {parsed!r}"
    assert parsed.get("city") == "Paris", parsed
    assert parsed.get("country") == "France", parsed
    print(f"\n[chat_json] {elapsed_ms:.0f}ms | parsed={parsed}")
    print(f"[chat_json] usage: {_usage_summary(client.chat(opts))}")


@_NEEDS_NETWORK_FLAG
@_NEEDS_API_KEY
def test_review_and_polish_smoke():
    """End-to-end review-and-polish flow mirroring im_reply_assistant.lua.

    Builds the same payload shape (``system`` + ``user`` with
    DRAFT_REPLY_START/END markers), sends it, and runs the structured
    content through ``_normalize_result``.
    """
    client = _client()
    draft = "i think we should maybe delay the launch to next week"

    user_content = "\n".join([
        "TASK: Rewrite the following IM draft reply in place.",
        "IMPORTANT: This text is my draft reply, not an incoming message to answer.",
        "OUTPUT: Return JSON only, following the schema from the system instruction.",
        "DRAFT_REPLY_START",
        draft,
        "DRAFT_REPLY_END",
    ])

    opts = ChatOptions(
        messages=[
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
        max_tokens=2048,
    )

    started = time.perf_counter()
    result = client.chat(opts)
    elapsed_ms = (time.perf_counter() - started) * 1000

    parsed = _normalize_result(result)

    assert parsed.polished.strip(), "polished text empty"
    assert isinstance(parsed.risk_check, list)
    assert isinstance(parsed.missing_info, list)
    # variants may be partial (model can omit some), but should be a dict
    assert isinstance(parsed.variants, dict)

    print(f"\n[review_and_polish] {elapsed_ms:.0f}ms")
    print(f"[review_and_polish] usage: {_usage_summary(result)}")
    print(f"[review_and_polish] risks:      {parsed.risk_check}")
    print(f"[review_and_polish] missing:    {parsed.missing_info}")
    print(f"[review_and_polish] polished:   {parsed.polished!r}")
    for key, value in parsed.variants.items():
        print(f"[review_and_polish] variant/{key}: {value!r}")
