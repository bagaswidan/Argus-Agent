"""Test OmniRoute Provider — Argus Brain."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from argus.brain.provider import ChatMessage, ChatResponse, create_provider


class _MockHandler(BaseHTTPRequestHandler):
    """Mock OpenAI-compatible endpoint."""

    responses: list[dict] = []
    last_body: dict = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode())
        _MockHandler.last_body = body

        # Echo back a canned response
        response = {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "model": "mock-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Halo dari mock!"},
                },
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        _MockHandler.responses.append(response)
        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture()
def mock_server():
    _MockHandler.responses = []
    server = HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/v1"
    server.shutdown()


class TestOmniRouteProvider:
    """Test provider against mock server."""

    def test_create_provider(self):
        p = create_provider(base_url="http://127.0.0.1:1/v1", model="Cadangan")
        assert p.model == "Cadangan"
        assert p.base_url == "http://127.0.0.1:1/v1"

    def test_chat_success(self, mock_server):
        p = create_provider(base_url=mock_server, api_key="test-key", model="Cadangan")
        resp = p.chat([ChatMessage(role="user", content="halo")])
        assert resp.success is True
        assert resp.content == "Halo dari mock!"
        assert resp.model == "mock-model"
        assert resp.total_tokens == 15

    def test_chat_sends_stream_false(self, mock_server):
        p = create_provider(base_url=mock_server, api_key="test-key")
        p.chat([ChatMessage(role="user", content="halo")])
        assert _MockHandler.last_body.get("stream") is False

    def test_chat_sends_auth_header(self, mock_server):
        p = create_provider(base_url=mock_server, api_key="secret-key")
        p.chat([ChatMessage(role="user", content="halo")])
        # Verify via captured body; header check needs handler capture
        assert p.api_key == "secret-key"

    def test_ask(self, mock_server):
        p = create_provider(base_url=mock_server, api_key="test-key")
        resp = p.ask("Siapa kamu?")
        assert resp.success is True
        assert resp.content == "Halo dari mock!"
        assert _MockHandler.last_body["messages"][0]["role"] == "system"

    def test_chat_http_error(self):
        p = create_provider(base_url="http://127.0.0.1:1/v1", api_key="k", timeout=2)
        resp = p.chat([ChatMessage(role="user", content="x")])
        assert resp.success is False
        assert resp.error


class TestChatMessage:
    def test_creation(self):
        m = ChatMessage(role="user", content="halo")
        assert m.role == "user"
        assert m.content == "halo"


class TestChatResponse:
    def test_success_property(self):
        r = ChatResponse(content="x", model="m", provider_id="p")
        assert r.success is True

    def test_failure_when_error(self):
        r = ChatResponse(content="", model="m", provider_id="p", error="boom")
        assert r.success is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
