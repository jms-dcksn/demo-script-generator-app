# Demo Script Generator

A chat-based web app that researches product pages, interviews users about their product, and generates structured demo scripts for sales engineers. Scripts follow an opinionated structure built on proven frameworks (3 Key Ideas, Tell-Show-Tell, limbic opening).

Built with a [Ralph Loop](https://github.com/ClaytonFarr/ralph-playbook) and Agent Teams.

**Try it live:** https://demo-script-generator-app.vercel.app/

## How it works

1. Provide product context -- a website URL, uploaded files, or a description
2. The app researches your product and asks clarifying questions
3. It generates a structured demo script tailored for sales engineers

## Stack

- **Frontend**: Next.js (App Router) -- streaming chat UI
- **Backend**: Python FastAPI -- SSE streaming to OpenAI LLM
- **Infra**: Docker Compose (two services), no database, no auth

## Quick start

```bash
# Copy env file and add your OpenAI API key
cp .env.example .env

# Start with Docker
docker-compose up --build

# Or use the convenience scripts
./start.sh
./stop.sh
```

The app runs at `http://localhost:3000`.
