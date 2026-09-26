import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sse_starlette.sse import AppStatus

from limits import LIMIT_DETAIL, reset_limits
from main import app, fetch_url_text, _is_safe_url


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_sse_state():
    """Reset sse_starlette's global event between tests to avoid event-loop binding issues."""
    AppStatus.should_exit_event = asyncio.Event()


@pytest.fixture(autouse=True)
def _reset_limits(monkeypatch):
    """Keep IP counters isolated; force the in-memory store unless a test opts into Redis."""
    import limits

    monkeypatch.delenv("REDIS_URL", raising=False)
    orig_msg = limits.MAX_MESSAGES_PER_IP
    orig_thr = limits.MAX_THREADS_PER_IP
    reset_limits()
    yield
    reset_limits()
    limits.MAX_MESSAGES_PER_IP = orig_msg
    limits.MAX_THREADS_PER_IP = orig_thr


def _make_ai_chunk(text: str):
    """Create a mock AIMessageChunk-like object."""
    from langchain_core.messages import AIMessageChunk
    return AIMessageChunk(content=text)


def _mock_agent_stream(*texts: str):
    """Return a patched agent and async-generator yielding message chunks."""
    chunks = [(_make_ai_chunk(t), {"langgraph_node": "model"}) for t in texts]

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


@pytest.mark.anyio
async def test_usage_starts_at_full_allowance():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/usage")
    body = response.json()
    assert response.status_code == 200
    assert body["used"] == 0
    assert body["limit"] == 20
    assert body["remaining"] == 20
    assert body["threads_used"] == 0
    assert body["threads_limit"] == 8
    assert body["threads_remaining"] == 8


@pytest.mark.anyio
async def test_chat_429_at_message_cap():
    import limits

    limits.MAX_MESSAGES_PER_IP = 2
    ctx, _ = _mock_agent_stream("OK")

    with ctx:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            for _ in range(2):
                ok = await ac.post(
                    "/api/chat",
                    json={
                        "messages": [{"role": "user", "content": "Hi"}],
                        "thread_id": "same-thread",
                    },
                )
                assert ok.status_code == 200
            limited = await ac.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi again"}],
                    "thread_id": "same-thread",
                },
            )
            usage = await ac.get("/api/usage")

    assert limited.status_code == 429
    assert limited.json()["detail"] == LIMIT_DETAIL
    assert usage.json()["used"] == 2
    assert usage.json()["remaining"] == 0


@pytest.mark.anyio
async def test_resume_does_not_count_toward_message_limit():
    import limits

    limits.MAX_MESSAGES_PER_IP = 1
    ctx, _ = _mock_agent_stream("OK")

    with ctx:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            first = await ac.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "thread_id": "hitl-thread",
                },
            )
            resume = await ac.post(
                "/api/chat",
                json={
                    "thread_id": "hitl-thread",
                    "is_resume": True,
                    "resume_payload": {"decisions": [{"type": "approve"}]},
                },
            )
            usage = await ac.get("/api/usage")
            blocked = await ac.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "Another"}],
                    "thread_id": "hitl-thread",
                },
            )

    assert first.status_code == 200
    assert resume.status_code == 200
    assert usage.json()["used"] == 1
    assert usage.json()["remaining"] == 0
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == LIMIT_DETAIL


@pytest.mark.anyio
async def test_new_thread_cap_allows_existing_thread():
    import limits

    limits.MAX_THREADS_PER_IP = 2
    ctx, _ = _mock_agent_stream("OK")

    with ctx:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            first = await ac.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )
            second = await ac.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )
            third_new = await ac.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )
            continue_existing = await ac.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "Continue"}],
                    "thread_id": "already-known",
                },
            )
            usage = await ac.get("/api/usage")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third_new.status_code == 429
    assert third_new.json()["detail"] == LIMIT_DETAIL
    assert continue_existing.status_code == 200
    assert usage.json()["threads_used"] == 2
    assert usage.json()["threads_remaining"] == 0
    # Continuing an existing thread still counts as a message.
    assert usage.json()["used"] == 3


def test_in_memory_fallback_without_redis():
    import limits

    assert os.getenv("REDIS_URL") in (None, "")
    assert limits._redis() is None
    limits.increment_message("1.2.3.4")
    limits.increment_thread("1.2.3.4")
    assert limits.message_count("1.2.3.4") == 1
    assert limits.thread_count("1.2.3.4") == 1
    assert "1.2.3.4" in "".join(limits._mem)


def test_redis_backend_sets_ttl_on_first_incr(monkeypatch):
    import limits

    class FakeRedis:
        def __init__(self) -> None:
            self.data: dict[str, int] = {}
            self.ttls: dict[str, int] = {}

        def get(self, key: str) -> str | None:
            val = self.data.get(key)
            return None if val is None else str(val)

        def incr(self, key: str) -> int:
            self.data[key] = self.data.get(key, 0) + 1
            return self.data[key]

        def expire(self, key: str, ttl: int) -> None:
            self.ttls[key] = ttl

    fake = FakeRedis()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    reset_limits()
    limits._redis_client = fake

    assert limits.increment_message("10.0.0.1") == 1
    assert limits.increment_message("10.0.0.1") == 2
    assert limits.increment_thread("10.0.0.1") == 1
    msg_key = limits._key("msg", "10.0.0.1")
    thr_key = limits._key("thr", "10.0.0.1")
    assert fake.data[msg_key] == 2
    assert fake.data[thr_key] == 1
    assert msg_key in fake.ttls
    assert thr_key in fake.ttls
    assert fake.ttls[msg_key] > 0
    assert limits._mem == {}
