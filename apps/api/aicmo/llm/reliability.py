"""Shared LLM client reliability policy (Phase 7.6).

One source of truth for the timeout + retry behaviour every provider client is
built with, so the agent, advisor, brain and worker paths all behave the same.

We configure each SDK's OWN retry layer rather than wrapping calls in a second
retry loop — that keeps exponential backoff, jitter and Retry-After handling
(which the Anthropic/OpenAI SDKs implement) while guaranteeing there is exactly
ONE retry layer, so retries cannot multiply across SDK + app + worker.

Retries target only TRANSIENT failures (timeouts, connection resets, 408/409/429
and 5xx). Permanent failures — 400 bad request, 401/403 auth, 404, 422 schema —
are never retried: the SDKs already classify these, and for the one SDK where we
pass an explicit list (Google) we deliberately omit them.
"""

from __future__ import annotations

# A single request may not hang the agent turn or a worker job indefinitely. The
# SDK default is ~600s; 60s is generous for a bounded structured-output call and
# turns an indefinite stall into a visible, bounded failure.
LLM_REQUEST_TIMEOUT_SECONDS: float = 60.0

# Number of RETRIES after the first attempt (Anthropic/OpenAI semantics). Total
# attempts = 1 + LLM_MAX_RETRIES. Kept small so exhausted retries fail fast and
# visibly instead of amplifying provider load during an outage.
LLM_MAX_RETRIES: int = 3

# Transient HTTP statuses worth retrying. Intentionally excludes 400/401/403/404
# and 422 (permanent — retrying cannot help and would waste quota).
LLM_RETRYABLE_STATUS: tuple[int, ...] = (408, 409, 429, 500, 502, 503, 504)


def google_http_options():
    """Build google-genai HttpOptions with an explicit timeout + a bounded,
    jittered, exponential-backoff retry policy over transient statuses only.
    (Anthropic/OpenAI get the same intent via their native timeout+max_retries.)"""
    from google.genai import types as genai_types

    return genai_types.HttpOptions(
        timeout=int(LLM_REQUEST_TIMEOUT_SECONDS * 1000),  # google expects milliseconds
        retry_options=genai_types.HttpRetryOptions(
            attempts=1 + LLM_MAX_RETRIES,  # google counts total attempts
            initial_delay=0.5,
            max_delay=8.0,
            exp_base=2.0,
            jitter=1.0,
            http_status_codes=list(LLM_RETRYABLE_STATUS),
        ),
    )
