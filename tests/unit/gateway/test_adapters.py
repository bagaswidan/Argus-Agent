"""Test Gateway Adapters — Argus."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from argus.gateway.adapters import (
    AdapterRegistry,
    PlatformAdapter,
    PlatformMessage,
    PlatformResponse,
    PlatformType,
    adapter_registry,
    create_adapter,
    register_adapter,
)


class MockAdapter(PlatformAdapter):
    """Mock adapter for testing."""

    def __init__(self, platform_type: PlatformType, config: dict[str, Any]):
        super().__init__(platform_type, config)
        self.connect_called = False
        self.disconnect_called = False
        self.send_called = False
        self.messages_sent = []

    @property
    def platform_name(self) -> str:
        return "Mock Platform"

    async def connect(self) -> bool:
        self.connect_called = True
        self._running = True
        return True

    async def disconnect(self) -> None:
        self.disconnect_called = True
        self._running = False

    async def send_message(self, response: PlatformResponse) -> bool:
        self.send_called = True
        self.messages_sent.append(response)
        return True

    async def get_updates(self) -> list[PlatformMessage]:
        return []


class TestPlatformMessage:
    """Test PlatformMessage dataclass."""

    def test_creation(self):
        msg = PlatformMessage(
            platform=PlatformType.TELEGRAM,
            platform_message_id="msg-123",
            sender_id="user-456",
            chat_id="chat-789",
            text="Hello",
        )
        assert msg.platform == PlatformType.TELEGRAM
        assert msg.text == "Hello"

    def test_default_timestamp(self):
        msg = PlatformMessage(
            platform=PlatformType.TELEGRAM,
            platform_message_id="msg-123",
            sender_id="user-456",
            chat_id="chat-789",
            text="Hello",
        )
        assert msg.timestamp is not None


class TestPlatformResponse:
    """Test PlatformResponse dataclass."""

    def test_creation(self):
        resp = PlatformResponse(
            chat_id="chat-789",
            text="Response",
            reply_to_message_id="msg-123",
        )
        assert resp.chat_id == "chat-789"
        assert resp.text == "Response"
        assert resp.reply_to_message_id == "msg-123"


class TestPlatformAdapter:
    """Test PlatformAdapter base class."""

    @pytest.mark.asyncio
    async def test_lifecycle(self):
        adapter = MockAdapter(PlatformType.CUSTOM, {})
        assert adapter.is_running is False
        assert adapter.is_connected is False

        await adapter.connect()
        assert adapter.is_running is True
        assert adapter.connect_called is True

        await adapter.disconnect()
        assert adapter.is_running is False
        assert adapter.disconnect_called is True

    @pytest.mark.asyncio
    async def test_send_message(self):
        adapter = MockAdapter(PlatformType.CUSTOM, {})
        await adapter.connect()

        response = PlatformResponse(chat_id="chat-1", text="Test")
        result = await adapter.send_message(response)
        assert result is True
        assert adapter.send_called is True
        assert len(adapter.messages_sent) == 1

    def test_set_message_handler(self):
        adapter = MockAdapter(PlatformType.CUSTOM, {})
        handler = MagicMock()
        adapter.set_message_handler(handler)
        assert adapter._message_handler == handler


class TestAdapterRegistry:
    """Test AdapterRegistry."""

    def test_register_and_get(self):
        registry = AdapterRegistry()
        registry.register(PlatformType.TELEGRAM, MockAdapter)

        adapter_class = registry.get(PlatformType.TELEGRAM)
        assert adapter_class == MockAdapter

    def test_get_unregistered(self):
        registry = AdapterRegistry()
        adapter_class = registry.get(PlatformType.DISCORD)
        assert adapter_class is None

    def test_create_adapter(self):
        registry = AdapterRegistry()
        registry.register(PlatformType.TELEGRAM, MockAdapter)

        adapter = registry.create(PlatformType.TELEGRAM, {"token": "test"})
        assert isinstance(adapter, MockAdapter)
        assert adapter.config == {"token": "test"}

    def test_list_registered(self):
        registry = AdapterRegistry()
        registry.register(PlatformType.TELEGRAM, MockAdapter)
        registry.register(PlatformType.DISCORD, MockAdapter)

        registered = registry.list_registered()
        assert PlatformType.TELEGRAM in registered
        assert PlatformType.DISCORD in registered
        assert len(registered) == 2


class TestGlobalRegistry:
    """Test global adapter registry functions."""

    def test_register_and_create(self):
        # Clean up
        adapter_registry._adapters.clear()

        class AnotherMockAdapter(PlatformAdapter):
            @property
            def platform_name(self) -> str:
                return "Another Mock"

            async def connect(self) -> bool:
                return True

            async def disconnect(self) -> None:
                pass

            async def send_message(self, response: PlatformResponse) -> bool:
                return True

            async def get_updates(self) -> list[PlatformMessage]:
                return []

        register_adapter(PlatformType.WEBHOOK, AnotherMockAdapter)
        adapter = create_adapter(PlatformType.WEBHOOK, {})
        assert isinstance(adapter, AnotherMockAdapter)

        # Cleanup
        adapter_registry._adapters.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
