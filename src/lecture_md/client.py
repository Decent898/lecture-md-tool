"""Shared HTTP client for OpenAI-compatible chat-completions endpoints."""

import time
from typing import Any

import requests


RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def chat_completions(
    *,
    base_url: str,
    api_key: str,
    payload: dict[str, Any],
    retries: int = 12,
    retry_sleep: float = 30.0,
    timeout: float = 600.0,
) -> dict[str, Any]:
    """POST to ``{base_url}/chat/completions`` with retry on transient errors."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response: requests.Response | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt >= retries:
                raise
            wait = retry_sleep * (attempt + 1)
            print(f"  request failed ({exc}); retrying in {wait:.0f}s", flush=True)
            time.sleep(wait)
            continue
        if response.status_code not in RETRYABLE_STATUS:
            break
        if attempt >= retries:
            break
        wait = retry_sleep * (attempt + 1)
        print(f"  HTTP {response.status_code}; retrying in {wait:.0f}s", flush=True)
        time.sleep(wait)
    assert response is not None
    if response.status_code >= 400:
        raise RuntimeError(f"API HTTP {response.status_code}: {response.text[:1000]}")
    return response.json()


def message_content(data: dict[str, Any]) -> str:
    """Extract the assistant message content from a chat-completions response."""
    return (data["choices"][0]["message"].get("content") or "").strip()
