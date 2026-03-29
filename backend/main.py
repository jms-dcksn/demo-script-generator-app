import asyncio
import base64
import json
import logging
import mimetypes
import os
import uuid
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langchain.messages import AIMessageChunk, HumanMessage, SystemMessage
from langgraph.types import Command
from starlette.datastructures import UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from agent import agent

logger = logging.getLogger(__name__)

app = FastAPI()

# In-memory rate limiting by IP
MAX_MESSAGES_PER_IP = int(os.getenv("MAX_MESSAGES_PER_IP", "20"))
_ip_usage: dict[str, int] = defaultdict(int)


def _client_ip(request: Request) -> str:
    """Extract client IP using Fly's trusted header, falling back for local dev."""
    fly_ip = request.headers.get("fly-client-ip")
    if fly_ip:
        return fly_ip.strip()
    return request.client.host if request.client else "unknown"

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


@app.get("/api/usage")
async def usage(request: Request) -> dict[str, int]:
    ip = _client_ip(request)
    used = _ip_usage[ip]
    return {"used": used, "limit": MAX_MESSAGES_PER_IP, "remaining": max(0, MAX_MESSAGES_PER_IP - used)}


@app.post("/api/chat", response_model=None)
async def chat(request: Request) -> EventSourceResponse | JSONResponse:
    ip = _client_ip(request)
    if _ip_usage[ip] >= MAX_MESSAGES_PER_IP:
        return JSONResponse(
            status_code=429,
            content={"detail": "You've reached the free demo limit. Thanks for trying it out!"},
        )
    content_type = request.headers.get("content-type", "")

    uploaded_files: list[UploadFile] = []
    if "multipart/form-data" in content_type:
        form = await request.form()
        raw_messages = form.get("messages", "")
        msg_list = json.loads(raw_messages) if raw_messages else []  # type: ignore[arg-type]
        raw_urls = str(form.get("urls", ""))
        urls: list[str] = json.loads(raw_urls) if raw_urls else []
        single_url = str(form.get("url", ""))
        if single_url and not urls:
            urls = [single_url]
        uploaded_files = [v for v in form.getlist("files") if isinstance(v, UploadFile)]
        thread_id = str(form.get("thread_id", ""))
        is_resume = str(form.get("is_resume", "false")).lower() == "true"
        raw_resume = str(form.get("resume_payload", ""))
        resume_payload = json.loads(raw_resume) if raw_resume else None
    else:
        body: dict[str, Any] = await request.json()
        msg_list = body.get("messages", [])
        urls = body.get("urls", [])
        single_url = body.get("url", "")
        if single_url and not urls:
            urls = [single_url]
        thread_id = body.get("thread_id", "")
        is_resume = body.get("is_resume", False)
        resume_payload = body.get("resume_payload", None)

    if not thread_id:
        thread_id = uuid.uuid4().hex

    config = {"configurable": {"thread_id": thread_id}}

    # On resume, skip context building -- just resume the graph
    if is_resume and resume_payload is not None:
        # Don't count resume toward rate limit
        async def resume_generator():
            try:
                async for chunk in agent.astream(
                    Command(resume=resume_payload),
                    config=config,
                    stream_mode="messages",
                ):
                    msg, metadata = chunk
                    if isinstance(msg, AIMessageChunk) and msg.content and metadata.get("langgraph_node") == "model":
                        yield {"data": json.dumps({"content": msg.content})}
            except Exception as e:
                logger.exception("Error during agent resume: %s", e)
                yield {"data": json.dumps({"error": str(e)})}
                return

            # Check for interrupt after stream
            state = agent.get_state(config)
            for task in state.tasks or []:
                for intr in task.interrupts or []:
                    yield {"data": json.dumps({
                        "interrupt": intr.value,
                        "thread_id": thread_id,
                    })}
                    return

            yield {"data": "[DONE]"}

        return EventSourceResponse(resume_generator())

    # -- Build context for the agent --

    # Fetch all URLs concurrently
    url_context: list[str] = []
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
                url_context.append(f"Product website content from {fetched_url}:\n\n{page_text}")
            else:
                url_context.append(f"(Could not fetch URL: {fetched_url})")

    # Process file uploads
    file_context_parts: list[str] = []
    image_parts: list[dict[str, Any]] = []
    for file in uploaded_files:
        data = await file.read()
        mime = _mime_type(file)
        if mime in IMAGE_TYPES:
            b64 = base64.b64encode(data).decode()
            image_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })
        else:
            try:
                text = data.decode("utf-8", errors="replace")[:8000]
                file_context_parts.append(f"--- File: {file.filename} ---\n{text}")
            except Exception:
                file_context_parts.append(
                    f"--- File: {file.filename} ---\n(binary file, could not extract text)"
                )

    # Build input messages for the agent
    input_messages: list = []

    # Inject URL and file context as system messages
    for ctx in url_context:
        input_messages.append(SystemMessage(content=ctx))
    if file_context_parts:
        input_messages.append(
            SystemMessage(content="Uploaded documents:\n\n" + "\n\n".join(file_context_parts))
        )

    # Add the latest user message (agent checkpointer handles history)
    user_text = msg_list[-1]["content"] if msg_list else ""
    if image_parts:
        input_messages.append(HumanMessage(content=[
            {"type": "text", "text": user_text},
            *image_parts,
        ]))
    else:
        input_messages.append(HumanMessage(content=user_text))

    _ip_usage[ip] += 1

    async def event_generator():
        # Send thread_id so frontend can track it
        yield {"data": json.dumps({"thread_id": thread_id})}

        try:
            async for chunk in agent.astream(
                {"messages": input_messages},
                config=config,
                stream_mode="messages",
            ):
                msg, metadata = chunk
                if isinstance(msg, AIMessageChunk) and msg.content and metadata.get("langgraph_node") == "model":
                    yield {"data": json.dumps({"content": msg.content})}
        except Exception as e:
            logger.exception("Error during agent stream: %s", e)
            yield {"data": json.dumps({"error": str(e)})}
            return

        # Check for interrupt after stream ends
        state = agent.get_state(config)
        for task in state.tasks or []:
            for intr in task.interrupts or []:
                yield {"data": json.dumps({
                    "interrupt": intr.value,
                    "thread_id": thread_id,
                })}
                return

        yield {"data": "[DONE]"}

    return EventSourceResponse(event_generator())
