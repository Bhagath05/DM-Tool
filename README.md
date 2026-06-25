# AI-CMO

Autonomous AI marketing platform. Monorepo containing the Next.js dashboard and the FastAPI backend.

## Stack

| Layer       | Choice                                                   |
| ----------- | -------------------------------------------------------- |
| Frontend    | Next.js 15 (App Router), TypeScript, Tailwind, shadcn/ui |
| Backend     | FastAPI, Python 3.12, SQLAlchemy 2, Alembic              |
| Auth        | Clerk (frontend SDK + backend JWT verification)          |
| Database    | PostgreSQL 16                                            |
| Job queue   | Arq (Redis-backed async workers)                         |
| LLM router  | Anthropic Claude (default), OpenAI, Gemini               |
| Build       | Turborepo + pnpm workspaces                              |

## Layout

```
apps/
  web/                Next.js dashboard
  api/                FastAPI backend
packages/             (Shared TS packages — added as needed)
infra/
  docker-compose.yml  Postgres + Redis for local dev
```

## Prerequisites

- Node 20+, pnpm 9+
- Python 3.12, uv
- Docker (for local Postgres + Redis)

## First-time setup

```bash
# 1. Install JS deps
pnpm install

# 2. Install Python deps for the API
cd apps/api && uv sync && cd ../..

# 3. Copy env template
cp .env.example .env
# Then fill in Clerk + LLM keys.

# 4. Start local Postgres + Redis
pnpm infra:up

# 5. Run DB migrations
cd apps/api && uv run alembic upgrade head && cd ../..

# 6. Start everything
pnpm dev
```

The web app runs on http://localhost:3000 and the API on http://localhost:8000.
API docs (Swagger) are at http://localhost:8000/docs.

## Architecture conventions

See [CLAUDE.md](./CLAUDE.md) for the conventions every module follows
(structured LLM outputs, async-first handlers, modular package layout).
