import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sse_starlette.sse import AppStatus

from main import app, fetch_url_text


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_sse_state():
    """Reset sse_starlette's global event between tests to avoid event-loop binding issues."""
    AppStatus.should_exit_event = asyncio.Event()


def _mock_openai_stream(*texts: str):
    """Return a patched client and async-generator yielding the given text chunks."""
    chunks = []
    for t in texts:
        c = MagicMock()
        c.choices = [MagicMock(delta=MagicMock(content=t))]
        chunks.append(c)

    async def stream():
        for c in chunks:
            yield c

    ctx = patch("main.client")
    return ctx, stream()


@pytest.mark.anyio
async def test_health():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_chat_streams_response():
    ctx, stream = _mock_openai_stream("Hello", " world")

    with ctx as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=stream)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        lines = response.text.strip().split("\n")
        data_lines = [line for line in lines if line.startswith("data:")]
        assert len(data_lines) >= 2
        first = json.loads(data_lines[0].removeprefix("data:").strip())
        assert first["content"] == "Hello"


@pytest.mark.anyio
async def test_chat_with_url():
    """URL content is fetched and injected as system context."""
    ctx, stream = _mock_openai_stream("OK")

    with ctx as mock_client, patch("main.fetch_url_text", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = "Product page text"
        mock_client.chat.completions.create = AsyncMock(return_value=stream)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "url": "https://example.com",
                },
            )

        assert response.status_code == 200
        # Verify URL content was passed to OpenAI
        call_args = mock_client.chat.completions.create.call_args
        msgs = call_args.kwargs["messages"]
        url_msgs = [m for m in msgs if "Product website content" in str(m.get("content", ""))]
        assert len(url_msgs) == 1
        assert "Product page text" in url_msgs[0]["content"]


@pytest.mark.anyio
async def test_chat_with_file_upload():
    """Uploaded text files are injected as document context."""
    ctx, stream = _mock_openai_stream("OK")

    with ctx as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=stream)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/api/chat",
                data={
                    "messages": json.dumps([{"role": "user", "content": "Analyze this"}]),
                },
                files=[("files", ("notes.txt", b"Product notes here", "text/plain"))],
            )

        assert response.status_code == 200
        call_args = mock_client.chat.completions.create.call_args
        msgs = call_args.kwargs["messages"]
        doc_msgs = [m for m in msgs if "Uploaded documents" in str(m.get("content", ""))]
        assert len(doc_msgs) == 1
        assert "Product notes here" in doc_msgs[0]["content"]


@pytest.mark.anyio
async def test_chat_with_image_upload():
    """Uploaded images are attached as base64 image_url to the last user message."""
    ctx, stream = _mock_openai_stream("OK")

    with ctx as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=stream)

        # 1x1 red PNG
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/api/chat",
                data={
                    "messages": json.dumps([{"role": "user", "content": "What is this?"}]),
                },
                files=[("files", ("screenshot.png", png_bytes, "image/png"))],
            )

        assert response.status_code == 200
        call_args = mock_client.chat.completions.create.call_args
        msgs = call_args.kwargs["messages"]
        last_user = [m for m in msgs if m["role"] == "user"][-1]
        # Content should be a list with text + image_url
        assert isinstance(last_user["content"], list)
        assert last_user["content"][0]["type"] == "text"
        assert last_user["content"][1]["type"] == "image_url"
        assert last_user["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.anyio
async def test_fetch_url_text():
    """fetch_url_text strips scripts/styles and returns visible text."""
    html = "<html><head><style>body{}</style></head><body><p>Hello</p><script>x()</script></body></html>"

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
        mock_resp.raise_for_status = MagicMock()

        mock_instance = AsyncMock()
        mock_instance.get = AsyncMock(return_value=mock_resp)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await fetch_url_text("https://example.com")

    assert "Hello" in result
    assert "<script>" not in result
    assert "body{}" not in result
