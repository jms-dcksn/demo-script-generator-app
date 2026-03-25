import base64
import json
import mimetypes
import os
from typing import Any

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from starlette.datastructures import UploadFile
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from sse_starlette.sse import EventSourceResponse

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
You are a demo script writing assistant. You help users create structured, \
compelling demo scripts for their products.

When a user provides product context (website URL, files, descriptions), your \
job is to craft a script following these best practices:

**3 Key Ideas**: Every great demo communicates at most 3 emotionally-attached \
ideas. Audiences cannot retain more. Identify the 3 most important ideas for \
the target audience.

**Tell-Show-Tell Structure**: For each key idea:
1. TELL -- state the idea and why it matters
2. SHOW -- demonstrate it live with a specific workflow
3. TELL -- recap the idea and its benefit

**Limbic Opening**: Start the script with an attention-grabbing opening that \
creates an emotional connection -- a surprising statistic, a relatable pain \
point, or a bold claim.

**Story Elements**: Weave in a user persona and their journey. The audience \
should see themselves (or their customer) in the story.

**Key Visuals / Data Points**: For each key idea, suggest specific screens, \
data, or visuals to show during the demo.

**Process**:
Before generating a script, ask clarifying questions to understand:
- Who is the target audience?
- What problem does the product solve?
- What are the top 3 capabilities to highlight?
- How long should the demo be?
- Any specific features or workflows to include?

Only generate the full script once you have enough context. When you do, \
output a well-structured document with clear sections.\
"""


IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


async def fetch_url_text(url: str) -> str:
    """Fetch a URL and return its visible text content."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as http:
        resp = await http.get(url)
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Truncate to ~8k chars to stay within context limits
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
        url = str(form.get("url", ""))
        uploaded_files = [v for v in form.getlist("files") if isinstance(v, UploadFile)]
    else:
        body: dict[str, Any] = await request.json()
        msg_list = body.get("messages", [])
        url = body.get("url", "")

    # Build OpenAI messages
    openai_messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    # Inject URL context if provided
    if url:
        try:
            page_text = await fetch_url_text(url)
            openai_messages.append({
                "role": "system",
                "content": f"Product website content from {url}:\n\n{page_text}",
            })
        except Exception:
            openai_messages.append({
                "role": "system",
                "content": f"(Could not fetch URL: {url})",
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
    if image_urls and openai_messages and openai_messages[-1]["role"] == "user":
        last = openai_messages[-1]
        last["content"] = [
            {"type": "text", "text": last["content"]},
            *image_urls,
        ]

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
