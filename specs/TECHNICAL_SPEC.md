# Technical Spec: Demo Script Generator

## Architecture

- **Frontend**: Next.js (App Router), single-page chat UI with streaming responses
- **Backend**: Python FastAPI, serves the LLM chat endpoint with SSE streaming
- **LLM**: OpenAI API (model TBD, API key provided later)
- **Infra**: Docker Compose with two services (frontend, backend), start/stop shell scripts for Mac
- **No database, no auth**

## Frontend (Next.js)

### Pages
- `/` — Single page with a chat interface

### Chat UI
- Message list (user + assistant messages)
- Input area: text input + send button
- File/image upload controls (for user to attach product context)
- URL input field for the company's product website
- Streaming assistant responses rendered incrementally
- Markdown rendering for assistant messages

### API Integration
- POST to backend `/api/chat` with message history + attachments
- Handle SSE/streaming response from backend

## Backend (FastAPI)

### Endpoints
- `POST /api/chat` — Accepts conversation history + attachments, streams LLM response
- `GET /health` — Health check

### LLM Integration
- OpenAI client with streaming
- System prompt encodes demo script best practices:
  - 3 Key Ideas framework
  - Tell-Show-Tell structure
  - Limbic opening
  - Story elements (user persona, benefit)
  - Key visuals/data points per idea
- The LLM asks clarifying questions before generating the final script
- Final output is a well-structured demo script (text)

### File Handling
- Accept uploaded files (images, documents) as base64 or multipart
- Accept a URL — backend can optionally scrape/summarize the product page

## Docker

- `docker-compose.yml` with `frontend` and `backend` services
- Frontend exposed on port 3000
- Backend exposed on port 8000
- `start.sh` / `stop.sh` scripts for Mac

## Environment
- `.env` file for `OPENAI_API_KEY`
- Frontend needs `NEXT_PUBLIC_API_URL` or proxies to backend
