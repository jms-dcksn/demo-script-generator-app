import asyncio
import base64
import json
import logging
import mimetypes
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from starlette.datastructures import UploadFile
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """\
You are an expert demo script writer. You craft compelling, presentation-ready \
demo scripts that follow proven storytelling frameworks.

You operate in two phases: DISCOVERY and SCRIPTING.

== PHASE 1: DISCOVERY ==

Before writing any script, you need to understand the product and audience. \
Gather this information through conversation, asking 1-3 focused questions per \
turn. Skip questions already answered by provided materials (website content, \
uploaded files, or the user's messages).

Key information to gather:
- Target audience (role, seniority, industry)
- Core problem the product solves and why it matters now
- Top 3 capabilities to highlight (or let you identify them from context)
- Demo length (default: 10 minutes if not specified)
- Specific workflows, screens, or features to include
- User persona for the story arc (who benefits and how)

If the user provides a website URL, uploaded files, or images, study that \
material carefully. Extract product positioning, features, and value props \
from it. Reference specific details from the provided materials in your script.

CRITICAL TRANSITION RULES:
- Discovery should last at most 2-4 exchanges. Do NOT keep asking questions \
beyond that. Once you have a reasonable picture, move to scripting immediately.
- If the user provides rich context upfront (e.g., a website URL with product \
details plus a description of their goals), skip discovery entirely and go \
straight to generating the script.
- When you decide you have enough context, do NOT ask for permission to proceed. \
Do NOT say "I'm ready to write the script" and wait. Instead, briefly state \
what you gathered (2-3 sentences max) and then IMMEDIATELY generate the full \
script in the same response.
- You can always make reasonable assumptions for missing details (use defaults \
like 10-minute length, general business audience) and note your assumptions \
at the top of the script. It is always better to produce a script that can be \
refined than to keep asking questions.

== PHASE 2: SCRIPTING ==

Generate a complete demo script with this structure:

### LIMBIC OPENING (30-60 seconds)
An attention-grabbing hook that creates emotional resonance: a surprising \
statistic, a relatable pain point, or a bold claim. This must make the \
audience lean in before any product is shown.

### INITIAL TELL (1-2 minutes)
Set the stage. Introduce the user persona and their challenge. Preview the \
3 key ideas the audience will see demonstrated. Frame what they are about \
to witness and why it matters.

### SHOW: KEY IDEAS (bulk of the demo)
For each of the 3 Key Ideas, use Tell-Show-Tell:

**Key Idea [N]: [Title]**
- TELL: State the idea and why the audience should care (1-2 sentences)
- SHOW: Step-by-step walkthrough of the live demonstration
  - Include [STAGE DIRECTION] annotations for presenter actions
  - Specify exact screens, clicks, and data to show
  - Note key visuals or data points that bring the idea to life
- TELL: Recap what was just shown and connect it to the audience's world

### CLOSING TELL (1-2 minutes)
Summarize the 3 key ideas. Reinforce the transformation: where the audience \
started (the problem) vs. where they are now (the solution). End with a clear \
call to action.

### PREPARATION CHECKLIST
List what the presenter needs ready: demo environment state, sample data, \
browser tabs, specific accounts or configurations.

== FORMATTING RULES ==
- Write in second person ("You will show..." / "Click on...")
- Use [STAGE DIRECTION] for non-verbal presenter actions
- Use **bold** for key talking points the presenter must hit
- Keep individual talking points to 2-3 sentences max
- Include approximate timing for each section
- Every demo communicates exactly 3 key ideas -- audiences cannot retain more

== REFINEMENT ==
When the user asks for changes after the script is generated, output only \
the changed sections, not the entire script. Explain what changed and why.\
"""


IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def _is_safe_url(url: str) -> bool:
    """Reject non-HTTP schemes and private/loopback hosts (SSRF prevention)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname or ""
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "::1") or host.startswith("169.254."):
        return False
    return True


async def fetch_url_text(url: str) -> str:
    """Fetch a URL and return its visible text content."""
    if not _is_safe_url(url):
        raise ValueError(f"URL not allowed: {url}")
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as http:
        resp = await http.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type:
            # Return raw text for non-HTML responses (JSON, plain text, etc.)
            return resp.text[:8000]
        soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return text[:8000]


def _mime_type(file: UploadFile) -> str:
    if file.content_type:
        return file.content_type
    guess, _ = mimetypes.guess_type(file.filename or "")
    return guess or "application/octet-stream"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(request: Request) -> EventSourceResponse:
    content_type = request.headers.get("content-type", "")

    uploaded_files: list[UploadFile] = []
    if "multipart/form-data" in content_type:
        form = await request.form()
        raw_messages = form.get("messages", "")
        msg_list = json.loads(raw_messages) if raw_messages else []  # type: ignore[arg-type]
        raw_urls = str(form.get("urls", ""))
        urls: list[str] = json.loads(raw_urls) if raw_urls else []
        # Backward compat: single "url" field
        single_url = str(form.get("url", ""))
        if single_url and not urls:
            urls = [single_url]
        uploaded_files = [v for v in form.getlist("files") if isinstance(v, UploadFile)]
    else:
        body: dict[str, Any] = await request.json()
        msg_list = body.get("messages", [])
        urls = body.get("urls", [])
        # Backward compat: single "url" field
        single_url = body.get("url", "")
        if single_url and not urls:
            urls = [single_url]

    # Build OpenAI messages
    openai_messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    # Fetch all URLs concurrently
    if urls:
        async def _fetch_one(u: str) -> tuple[str, str | None]:
            try:
                text = await fetch_url_text(u)
                return (u, text)
            except Exception as e:
                logger.warning("Failed to fetch URL %s: %s", u, e)
                return (u, None)

        results = await asyncio.gather(*[_fetch_one(u) for u in urls])
        for fetched_url, page_text in results:
            if page_text is not None:
                openai_messages.append({
                    "role": "system",
                    "content": f"Product website content from {fetched_url}:\n\n{page_text}",
                })
            else:
                openai_messages.append({
                    "role": "system",
                    "content": f"(Could not fetch URL: {fetched_url})",
                })

    # Process file uploads into context
    file_context_parts: list[str] = []
    image_urls: list[dict[str, Any]] = []
    for file in uploaded_files:
        data = await file.read()
        mime = _mime_type(file)
        if mime in IMAGE_TYPES:
            b64 = base64.b64encode(data).decode()
            image_urls.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })
        else:
            # Treat as text document
            try:
                text = data.decode("utf-8", errors="replace")[:8000]
                file_context_parts.append(
                    f"--- File: {file.filename} ---\n{text}"
                )
            except Exception:
                file_context_parts.append(
                    f"--- File: {file.filename} ---\n(binary file, could not extract text)"
                )

    if file_context_parts:
        openai_messages.append({
            "role": "system",
            "content": "Uploaded documents:\n\n" + "\n\n".join(file_context_parts),
        })

    # Add conversation history
    for msg in msg_list:
        openai_messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })

    # If images were uploaded, attach them to the last user message
    if image_urls:
        for i in range(len(openai_messages) - 1, -1, -1):
            if openai_messages[i]["role"] == "user":
                openai_messages[i]["content"] = [
                    {"type": "text", "text": openai_messages[i]["content"]},
                    *image_urls,
                ]
                break

    async def event_generator():
        stream = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            messages=openai_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield {"data": json.dumps({"content": delta.content})}
        yield {"data": "[DONE]"}

    return EventSourceResponse(event_generator())
