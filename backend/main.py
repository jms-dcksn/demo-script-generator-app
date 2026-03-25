import json
import os
from typing import Any

from fastapi import FastAPI, Request
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(request: Request) -> EventSourceResponse:
    body: dict[str, Any] = await request.json()
    messages = body.get("messages", [])

    # Prepend system prompt
    openai_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in messages:
        openai_messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })

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
