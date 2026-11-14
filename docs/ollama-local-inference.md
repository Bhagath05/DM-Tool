# Ollama local inference (Phase 7.19)

DM Tool can route selected, lower-stakes LLM tasks to a **locally-running Ollama
model** instead of an external provider. It plugs into the existing
`apps/api/aicmo/llm/` router/policy — it is **not** a separate AI system.

It is **opt-in, disabled by default, and never the production default**.

---

## Why local inference

- Keep prompt/business data on the developer's machine (privacy).
- Zero marginal cost + offline development.
- A stepping stone to a secured, self-hosted inference server.

## What it is NOT

- Not the Render production default. Production keeps the external providers
  (`LLM_DEFAULT_PROVIDER`), because Render has no GPU and limited RAM.
- Not a route for high-stakes reasoning, deterministic calculations, RBAC,
  approvals, confidence calculations, or security decisions.

---

## Local setup

1. Install Ollama (https://ollama.com) and start the server. It binds to
   `127.0.0.1:11434` by default — **keep it loopback; do not expose the port.**
2. Pull a model (the current default):
   ```bash
   ollama pull llama3:latest
   ```
3. Verify it is running:
   ```bash
   curl http://127.0.0.1:11434/api/version
   ollama list
   ```

## Enable it in DM Tool

In the backend environment (e.g. root `.env`):

```bash
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://127.0.0.1:11434   # loopback by default
OLLAMA_MODEL=llama3:latest

# Route one or more ELIGIBLE tasks to Ollama (reuses the existing policy):
LLM_TASK_MODELS=creative_generation:ollama/llama3:latest
```

Restart the API. On boot it logs `ollama.enabled` (or `ollama.disabled`); a bad
config logs `ollama.config_invalid` and the app still boots — Ollama is never a
hard startup dependency.

## Change the local model

Pull another model and point `OLLAMA_MODEL` / `LLM_TASK_MODELS` at it, e.g.:

```bash
ollama pull qwen2.5:7b-instruct
# OLLAMA_MODEL=qwen2.5:7b-instruct
# LLM_TASK_MODELS=creative_generation:ollama/qwen2.5:7b-instruct
```

---

## Supported (eligible) tasks

Only a small, code-reviewed allowlist may run locally
(`OLLAMA_ELIGIBLE_TASKS` in `aicmo/llm/tasks.py`):

- `creative_generation`
- `agent_summarize`
- `business_research` (bounded context)

Routing any **other** task to `ollama` fails closed in the router. These stay on
external providers:

- `strategy_reasoning`, `intelligence`, `agent_plan`, `agent_reasoning`

Deterministic logic — revenue/financial math, RBAC, approvals, evidence
confidence (server-derived), security decisions — is plain Python and never
routed through any LLM.

## Fallback & privacy

By default a locally-routed task is **local-only**: if Ollama is disabled or
fails, the router raises a controlled error and **does not** silently send the
prompt to an external provider. To allow a specific task to fall back to the
external default LLM on failure, opt in explicitly:

```bash
OLLAMA_FALLBACK_TASKS=creative_generation
```

Provider failures are logged by task + failure type only — never the prompt or
business data.

---

## Limitations of the current 8B model (`llama3:latest`)

- **8K context window** (Llama 3.0) — large `business_research` prompts may not
  fit; keep local routing to bounded-context tasks.
- Weaker JSON-schema / tool-call fidelity than frontier models. Output is always
  validated with Pydantic (`model_validate`); invalid output is a controlled
  failure, never returned.
- On a 16 GB machine it needs ~5–6 GB resident — fine for dev, tight when the
  full stack is running. Consider `qwen2.5:7b-instruct` for stronger structured
  output.

## Future: a secured self-hosted inference server

To use a remote, self-hosted inference server (not loopback):

```bash
OLLAMA_ALLOW_NON_LOOPBACK=true
OLLAMA_BASE_URL=https://ollama.internal.example:11434
```

You are then responsible for securing that server:

- Terminate TLS; require authentication at a reverse proxy in front of Ollama.
- Keep it on a private network / VPN; never expose `11434` publicly.
- The base URL is **server configuration only** — DM Tool never accepts an
  Ollama endpoint from an HTTP request or the browser.
