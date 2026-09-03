#!/usr/bin/env python3
"""Probe candidate FREE OpenRouter models for availability + tool calling.

Why this exists
---------------
The configured generation model must satisfy three things at once: it must be
genuinely free (pricing 0/0), it must support forced tool calling (the whole
structured-output contract depends on it), and it must actually be serving
requests. The third is not visible from the model catalogue -- a model can be
listed, advertise `tools`/`tool_choice`, and still return HTTP 429
"temporarily rate-limited upstream" for every request.

This script checks all three so the choice of LLM_MODEL is an evidence-based,
reproducible decision rather than an assumption. It is a diagnostic tool: it
is never imported by the application and never runs as part of the test suite.

Usage
-----
    docker compose exec backend python3 scripts/probe_llm_models.py
    docker compose exec backend python3 scripts/probe_llm_models.py --attempts 5

Requires OPENROUTER_API_KEY in the environment (never printed).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402

CANDIDATES = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
]

PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "emit_probe",
        "description": "Emit a structured probe result.",
        "parameters": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}, "note": {"type": "string"}},
            "required": ["ok", "note"],
        },
    },
}


def catalogue(client: httpx.Client) -> dict:
    response = client.get("/models", timeout=30)
    response.raise_for_status()
    return {model["id"]: model for model in response.json()["data"]}


def probe_once(client: httpx.Client, model: str) -> tuple[bool, str]:
    """One forced-tool-call request. Returns (tool_call_produced, detail)."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Call emit_probe with ok=true and a one-word note."}],
        "tools": [PROBE_TOOL],
        "tool_choice": {"type": "function", "function": {"name": "emit_probe"}},
        "parallel_tool_calls": False,
        "temperature": 0,
        "max_tokens": 2000,
    }
    try:
        response = client.post("/chat/completions", json=payload, timeout=90)
    except httpx.HTTPError as exc:
        return False, f"{type(exc).__name__} (unreachable)"

    try:
        body = response.json()
    except ValueError:
        return False, f"HTTP {response.status_code}: non-JSON body"

    # OpenRouter reports some upstream failures as HTTP 200 with an `error`
    # envelope and no `choices`, so status alone is not enough.
    error = body.get("error")
    if response.status_code != 200 or isinstance(error, dict):
        error = error or {}
        raw = (error.get("metadata") or {}).get("raw") or error.get("message") or ""
        return False, f"HTTP {response.status_code} code={error.get('code')}: {str(raw)[:80]}"

    choice = (body.get("choices") or [{}])[0]
    tool_calls = (choice.get("message") or {}).get("tool_calls")
    if not tool_calls:
        return False, f"no tool_calls (finish_reason={choice.get('finish_reason')!r})"
    return True, f"tool_call ok (finish_reason={choice.get('finish_reason')!r})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=3, help="probe attempts per model")
    parser.add_argument("--delay", type=float, default=5.0, help="seconds between attempts")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY is not set -- cannot probe.")
        return 2

    client = httpx.Client(
        base_url=settings.openrouter_base_url,
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}", "Content-Type": "application/json"},
    )
    models = catalogue(client)

    print(f"configured LLM_MODEL: {settings.llm_model}\n")
    for model in CANDIDATES:
        entry = models.get(model)
        if entry is None:
            print(f"{model}\n  NOT LISTED in the OpenRouter catalogue\n")
            continue

        pricing = entry.get("pricing", {})
        free = str(pricing.get("prompt")) == "0" and str(pricing.get("completion")) == "0"
        supported = set(entry.get("supported_parameters") or [])
        advertises_tools = {"tools", "tool_choice"} <= supported

        successes = 0
        details: list[str] = []
        for attempt in range(args.attempts):
            ok, detail = probe_once(client, model)
            successes += int(ok)
            details.append(detail)
            if attempt < args.attempts - 1:
                time.sleep(args.delay)

        verdict = "USABLE" if (free and advertises_tools and successes == args.attempts) else "NOT USABLE"
        print(f"{model}")
        print(f"  free pricing (0/0):      {free}")
        print(f"  advertises tool calling: {advertises_tools}")
        print(f"  live tool calls:         {successes}/{args.attempts}")
        for i, detail in enumerate(details, start=1):
            print(f"    attempt {i}: {detail}")
        print(f"  verdict: {verdict}\n")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
