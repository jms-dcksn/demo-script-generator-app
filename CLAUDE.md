# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Demo Script Generator -- a chat-based web app that helps users create structured demo scripts for their products. Users provide product context (website URL, files, descriptions) and the LLM generates a script following best-practice frameworks (3 Key Ideas, Tell-Show-Tell, limbic opening).

## Architecture

- **Frontend**: Next.js (App Router) on port 3000 -- single-page streaming chat UI
- **Backend**: Python FastAPI on port 8000 -- SSE streaming to OpenAI LLM
- **Infra**: Docker Compose (two services), no database, no auth

Key endpoints:
- `POST /api/chat` -- conversation history + attachments in, SSE stream out
- `GET /health` -- health check

## Build & Run

```bash
# Full stack via Docker
docker-compose up --build

# Or use the convenience scripts
./start.sh    # start
./stop.sh     # stop

# Backend only
cd backend && pip install -r requirements.txt && uvicorn main:app --reload --port 8000

# Frontend only
cd frontend && npm install && npm run dev
```

## Validation

```bash
# Backend
cd backend && ruff check .
cd backend && mypy .

# Frontend
cd frontend && npm run lint
cd frontend && npx tsc --noEmit
```

## Ralph Loop (automated iteration)

This project uses `loop.sh` to run Claude CLI in headless mode, iterating through `IMPLEMENTATION_PLAN.md`:

```bash
./loop.sh              # build mode, runs until Ctrl+C
./loop.sh plan         # plan mode (analyze specs, update plan only)
./loop.sh build 10     # build mode, 10 iterations max
```

- `PROMPT_build.md` -- instructions for build iterations (implement, test, commit)
- `PROMPT_plan.md` -- instructions for plan iterations (analyze, update plan)
- `IMPLEMENTATION_PLAN.md` -- shared state between iterations; keep current

## Conventions

- Keep code simple. No overly defensive programming (skip isinstance checks, excessive validation)
- No emojis in code or docs
- Concise comments only where necessary
- Specs live in `specs/` (PRD.md, TECHNICAL_SPEC.md)
- When implementing, update IMPLEMENTATION_PLAN.md and AGENTS.md with operational findings

@AGENTS.md
