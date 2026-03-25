import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


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
    # Mock the OpenAI streaming response
    mock_chunk_1 = MagicMock()
    mock_chunk_1.choices = [MagicMock(delta=MagicMock(content="Hello"))]

    mock_chunk_2 = MagicMock()
    mock_chunk_2.choices = [MagicMock(delta=MagicMock(content=" world"))]

    async def mock_stream():
        yield mock_chunk_1
        yield mock_chunk_2

    mock_response = mock_stream()

    with patch("main.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        # Parse SSE events from the response body
        lines = response.text.strip().split("\n")
        data_lines = [line for line in lines if line.startswith("data:")]
        # Should have content chunks and a [DONE] marker
        assert len(data_lines) >= 2
        first = json.loads(data_lines[0].removeprefix("data:").strip())
        assert first["content"] == "Hello"
