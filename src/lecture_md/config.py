"""Configuration helpers for OpenAI-compatible API backends.

The tool talks to any OpenAI-compatible ``/v1/chat/completions`` endpoint.
Configuration is resolved in this order: CLI argument > environment variable >
built-in default.

Environment variables:

- ``LECTURE_MD_API_KEY``: API key. Falls back to ``OPENAI_API_KEY`` and the
  legacy ``MIMO_API_KEY``.
- ``LECTURE_MD_BASE_URL``: API base URL, e.g. ``https://api.openai.com/v1``.
- ``LECTURE_MD_ASR_MODEL``: chat model that accepts ``input_audio`` content.
- ``LECTURE_MD_CHAT_MODEL``: text chat model used for correction and notes.
- ``LECTURE_MD_TERMS``: comma-separated domain terms to guide correction.
"""

import os


_API_KEY_ENV_VARS = ("LECTURE_MD_API_KEY", "OPENAI_API_KEY", "MIMO_API_KEY")

FALLBACK_BASE_URL = "https://api.openai.com/v1"
FALLBACK_ASR_MODEL = "gpt-4o-mini-audio-preview"
FALLBACK_CHAT_MODEL = "gpt-4o-mini"

API_KEY_HINT = (
    "Set LECTURE_MD_API_KEY (or OPENAI_API_KEY) to an API key for an "
    "OpenAI-compatible endpoint, or run without API steps "
    "(--asr local --optimize none --notes none)."
)


def get_api_key() -> str | None:
    """Return the first configured API key, or None."""
    for name in _API_KEY_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def require_api_key() -> str:
    key = get_api_key()
    if not key:
        raise RuntimeError(API_KEY_HINT)
    return key


def default_base_url() -> str:
    return os.environ.get("LECTURE_MD_BASE_URL", "").strip() or FALLBACK_BASE_URL


def default_asr_model() -> str:
    return os.environ.get("LECTURE_MD_ASR_MODEL", "").strip() or FALLBACK_ASR_MODEL


def default_chat_model() -> str:
    return os.environ.get("LECTURE_MD_CHAT_MODEL", "").strip() or FALLBACK_CHAT_MODEL


def default_terms() -> str:
    return os.environ.get("LECTURE_MD_TERMS", "").strip()
