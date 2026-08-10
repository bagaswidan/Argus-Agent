"""Test Gateway Server — Argus."""
from __future__ import annotations

import pytest

from argus.gateway.server import GatewayServer, GatewayConfig, AIOHTTP_AVAILABLE


class TestGatewayConfig:
    """Test GatewayConfig."""

    def test_defaults(self):
        cfg = GatewayConfig()
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8080
        assert cfg.cors_origins == ["*"]
        assert cfg.max_message_size == 1048576
        assert cfg.request_timeout == 30

    def test_custom(self):
        cfg = GatewayConfig(host="0.0.0.0", port=9090, cors_origins=["https://example.com"])
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 9090
        assert cfg.cors_origins == ["https://example.com"]


class TestGatewayServer:
    """Test GatewayServer."""

    def test_create(self):
        cfg = GatewayConfig(host="127.0.0.1", port=18080)
        server = GatewayServer(cfg)
        assert server.config.host == "127.0.0.1"
        assert server.config.port == 18080
        assert server.is_running is False

    def test_create_with_auth(self):
        from argus.gateway.auth import create_auth_manager
        auth = create_auth_manager("test-secret")
        cfg = GatewayConfig(host="127.0.0.1", port=18081, auth=auth)
        server = GatewayServer(cfg)
        assert server.config.auth is not None

    def test_is_running_false_by_default(self):
        server = GatewayServer(GatewayConfig())
        assert server.is_running is False

    def test_status_dict(self):
        server = GatewayServer(GatewayConfig(host="127.0.0.1", port=18082))
        assert server.is_running is False

    def test_adapters_empty(self):
        server = GatewayServer(GatewayConfig())
        assert server._adapters == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])