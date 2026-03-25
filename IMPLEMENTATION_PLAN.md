# Implementation Plan

Items ordered by build priority (dependencies first).

## 1. Backend scaffold and core API
- [x] Scaffold FastAPI project (`backend/`) with `requirements.txt` and `Dockerfile`
- [x] Add CORS middleware allowing frontend origin
- [x] Implement `GET /health` endpoint
- [x] Write system prompt encoding demo script best practices (3 Key Ideas, Tell-Show-Tell, limbic opening, story elements, key visuals/data points, user persona/benefit). Prompt should instruct the LLM to ask clarifying questions before generating the final script.
- [x] Integrate OpenAI client with streaming completions
- [x] Implement `POST /api/chat` endpoint with streaming SSE response (accepts conversation history, streams back LLM reply)

## 2. Backend file and URL handling
- [x] Handle file/image uploads (multipart) and pass to LLM as context (base64 for images, text extraction for documents)
- [x] Handle product website URL input (pass as context to LLM; optionally scrape/summarize the page)

## 3. Frontend scaffold and chat UI
- [x] Scaffold Next.js app (`frontend/`) with App Router, `Dockerfile`, and `package.json`
- [x] Configure `NEXT_PUBLIC_API_URL` env var (default `http://localhost:8000`)
- [x] Build single-page chat UI: message list, text input area, send button
- [x] Implement streaming response handling (SSE from backend, incremental rendering)
- [x] Render assistant messages with Markdown formatting
- [x] Wire up POST to backend `/api/chat` with conversation history

## 4. Frontend inputs (URL and file uploads)
- [x] Add URL input field for company product website
- [x] Add file/image upload controls and send attachments with chat request

## 5. Infrastructure and packaging
- [ ] Create `.env.example` with `OPENAI_API_KEY` placeholder
- [ ] Create `docker-compose.yml` (frontend on port 3000, backend on port 8000, env passthrough)
- [ ] Create `start.sh` and `stop.sh` scripts for Mac
