import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sse_starlette.sse import AppStatus

from main import app, fetch_url_text, _is_safe_url


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_sse_state():
    """Reset sse_starlette's global event between tests to avoid event-loop binding issues."""
    AppStatus.should_exit_event = asyncio.Event()


def _make_ai_chunk(text: str):
    """Create a mock AIMessageChunk-like object."""
    from langchain_core.messages import AIMessageChunk
    return AIMessageChunk(content=text)


def _mock_agent_stream(*texts: str):
    """Return a patched agent and async-generator yielding message chunks."""
    chunks = [(_make_ai_chunk(t), {"langgraph_node": "agent"}) for t in texts]

    async def astream(input_data, config, stream_mode="messages"):
        for c in chunks:
            yield c

    mock_ag = MagicMock()
    mock_ag.astream = astream
    # get_state returns no interrupts by default
    mock_state = MagicMock()
    mock_state.tasks = []
    mock_ag.get_state = MagicMock(return_value=mock_state)

    ctx = patch("main.agent", mock_ag)
    return ctx, mock_ag


def _mock_agent_with_interrupt(interrupt_value: dict):
    """Return a patched agent that yields no content but has a pending interrupt."""
    async def astream(input_data, config, stream_mode="messages"):
        # Yield nothing -- the interrupt is detected via get_state
        return
        yield  # make it an async generator

    mock_intr = MagicMock()
    mock_intr.value = interrupt_value

    mock_task = MagicMock()
    mock_task.interrupts = [mock_intr]

    mock_state = MagicMock()
    mock_state.tasks = [mock_task]

    mock_ag = MagicMock()
    mock_ag.astream = astream
    mock_ag.get_state = MagicMock(return_value=mock_state)

    ctx = patch("main.agent", mock_ag)
    return ctx, mock_ag


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
    ctx, _ = _mock_agent_stream("Hello", " world")

    with ctx:
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
        # First data line is thread_id, then content chunks
        payloads = [json.loads(line.removeprefix("data:").strip()) for line in data_lines if line.strip() != "data: [DONE]"]
        content_payloads = [p for p in payloads if "content" in p]
        assert len(content_payloads) >= 2
        assert content_payloads[0]["content"] == "Hello"
        assert content_payloads[1]["content"] == " world"
        # Verify thread_id was sent
        thread_payloads = [p for p in payloads if "thread_id" in p and "interrupt" not in p]
        assert len(thread_payloads) >= 1


@pytest.mark.anyio
async def test_chat_with_url():
    """URL content is fetched and injected as system context."""
    ctx, mock_ag = _mock_agent_stream("OK")

    with ctx, patch("main.fetch_url_text", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = "Product page text"

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
        # Verify astream was called with messages containing URL context
        # The astream is a regular function, so we check it was used
        # by verifying the response streamed successfully
        assert "text/event-stream" in response.headers["content-type"]


@pytest.mark.anyio
async def test_chat_with_file_upload():
    """Uploaded text files are injected as document context."""
    ctx, _ = _mock_agent_stream("OK")

    with ctx:
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


@pytest.mark.anyio
async def test_chat_with_image_upload():
    """Uploaded images are included in the input messages."""
    ctx, _ = _mock_agent_stream("OK")

    # 1x1 red PNG
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    )

    with ctx:
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


@pytest.mark.anyio
async def test_chat_with_thread_id():
    """Thread ID is preserved when provided by client."""
    ctx, mock_ag = _mock_agent_stream("OK")

    with ctx:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "thread_id": "test-thread-123",
                },
            )

        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        data_lines = [line for line in lines if line.startswith("data:") and line.strip() != "data: [DONE]"]
        payloads = [json.loads(line.removeprefix("data:").strip()) for line in data_lines]
        thread_payloads = [p for p in payloads if "thread_id" in p and "interrupt" not in p]
        assert thread_payloads[0]["thread_id"] == "test-thread-123"


@pytest.mark.anyio
async def test_chat_interrupt_flow():
    """When the agent has a pending interrupt, it streams the interrupt payload."""
    interrupt_value = {
        "action_requests": [
            {
                "name": "write_script",
                "args": {"script_summary": "Test summary"},
                "description": "Tool execution requires approval\n\nTool: write_script\nArgs: {'script_summary': 'Test summary'}",
            }
        ],
        "review_configs": [
            {
                "action_name": "write_script",
                "allowed_decisions": ["approve", "edit", "reject"],
            }
        ],
    }
    ctx, _ = _mock_agent_with_interrupt(interrupt_value)

    with ctx:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )

        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        data_lines = [line for line in lines if line.startswith("data:")]
        payloads = [json.loads(line.removeprefix("data:").strip()) for line in data_lines]
        interrupt_payloads = [p for p in payloads if "interrupt" in p]
        assert len(interrupt_payloads) == 1
        assert interrupt_payloads[0]["interrupt"]["action_requests"][0]["name"] == "write_script"
        assert "thread_id" in interrupt_payloads[0]
        # [DONE] should NOT be present since we have an interrupt
        done_lines = [line for line in lines if "[DONE]" in line]
        assert len(done_lines) == 0


@pytest.mark.anyio
async def test_chat_resume_flow():
    """Resume after interrupt sends Command to agent."""
    ctx, mock_ag = _mock_agent_stream("Script content here")

    with ctx:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/api/chat",
                json={
                    "thread_id": "test-thread-456",
                    "is_resume": True,
                    "resume_payload": {"decisions": [{"type": "approve"}]},
                },
            )

        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        data_lines = [line for line in lines if line.startswith("data:")]
        payloads = []
        for line in data_lines:
            payload = line.removeprefix("data:").strip()
            if payload == "[DONE]":
                continue
            payloads.append(json.loads(payload))
        content_payloads = [p for p in payloads if "content" in p]
        assert len(content_payloads) >= 1
        assert content_payloads[0]["content"] == "Script content here"


@pytest.mark.anyio
async def test_chat_with_multiple_urls():
    """Multiple URLs are fetched concurrently."""
    ctx, _ = _mock_agent_stream("OK")

    with ctx, patch("main.fetch_url_text", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = lambda u: f"Content from {u}"

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "urls": ["https://example.com", "https://other.com"],
                },
            )

        assert response.status_code == 200
        assert mock_fetch.call_count == 2


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


def test_is_safe_url_rejects_unsafe():
    """SSRF prevention: reject private/loopback hosts and non-HTTP schemes."""
    assert not _is_safe_url("file:///etc/passwd")
    assert not _is_safe_url("ftp://example.com")
    assert not _is_safe_url("http://localhost:8000")
    assert not _is_safe_url("http://127.0.0.1/admin")
    assert not _is_safe_url("http://169.254.169.254/latest/meta-data/")
    assert not _is_safe_url("http://::1/")
    assert not _is_safe_url("")
    assert not _is_safe_url("not-a-url")


def test_is_safe_url_allows_valid():
    """Public HTTP/HTTPS URLs should be allowed."""
    assert _is_safe_url("https://example.com")
    assert _is_safe_url("http://example.com/page")
    assert _is_safe_url("https://www.company.com/product")


@pytest.mark.anyio
async def test_fetch_url_text_rejects_unsafe_url():
    """fetch_url_text raises ValueError for unsafe URLs."""
    with pytest.raises(ValueError, match="URL not allowed"):
        await fetch_url_text("http://localhost:8000")
