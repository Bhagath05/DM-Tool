# AI-CMO API

FastAPI backend.

## Layout

```
aicmo/
  main.py            FastAPI app + lifespan
  config.py          Pydantic Settings (env-driven)
  db/
    session.py       Async SQLAlchemy engine + sessionmaker
    base.py          DeclarativeBase + TimestampMixin
  auth/
    clerk.py         Clerk JWT verification (JWKS-cached)
  llm/
    router.py        Single entry for all LLM calls
    providers/       Anthropic (live), OpenAI/Google (stubs)
  queue/
    worker.py        Arq worker settings
  modules/           Feature modules go here (onboarding, trends, content, ...)
alembic/             Migrations
```

## Run

```bash
uv sync                       # install deps
uv run uvicorn aicmo.main:app --reload   # dev server on :8000
```

Or via the monorepo: `pnpm dev:api`.

## Adding a feature module

Follow the layout described in the root [CLAUDE.md](../../CLAUDE.md). Briefly:

```
aicmo/modules/<name>/
  router.py     # FastAPI APIRouter
  service.py    # Pure business logic
  schemas.py    # Pydantic request/response models
  models.py     # SQLAlchemy ORM
  prompts.py    # LLM prompts + structured output schemas
  tasks.py      # Arq jobs
```

Then:
1. Register the router in `aicmo/main.py`.
2. Import the ORM models in `aicmo/db/base.py` and `alembic/env.py`.
3. Append tasks to `WorkerSettings.functions` in `aicmo/queue/worker.py`.
4. Run `pnpm --filter @ai-cmo/api makemigration "add <name>"` then `migrate`.
