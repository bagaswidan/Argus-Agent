"""Platform Adapters — Argus Gateway.

Abstract base class and registry for platform-specific connectors
(Telegram, Discord, Slack, WhatsApp, etc.).
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


class PlatformType(StrEnum):
    """Supported platform types."""

    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    SIGNAL = "signal"
    MATRIX = "matrix"
    WEBHOOK = "webhook"
    CUSTOM = "custom"


@dataclass
class PlatformMessage:
    """Incoming message from a platform."""

    platform: PlatformType
    platform_message_id: str
    sender_id: str
    chat_id: str
    text: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] | None = None


@dataclass
class PlatformResponse:
    """Outgoing response to a platform."""

    chat_id: str
    text: str
    reply_to_message_id: str | None = None
    parse_mode: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PlatformAdapter(ABC):
    """Abstract base class for platform adapters."""

    def __init__(
        self,
        platform_type: PlatformType,
        config: dict[str, Any],
    ):
        self.platform_type = platform_type
        self.config = config
        self._running = False
        self._message_handler: Callable[[PlatformMessage], Any] | None = None

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable platform name."""

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the platform."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the platform."""

    @abstractmethod
    async def send_message(self, response: PlatformResponse) -> bool:
        """Send a message to the platform."""

    @abstractmethod
    async def get_updates(self) -> list[PlatformMessage]:
        """Poll for new messages (for polling-based platforms)."""

    def set_message_handler(
        self, handler: Callable[[PlatformMessage], Any],
    ) -> None:
        """Set the async handler for incoming messages."""
        self._message_handler = handler

    async def _handle_message(self, message: PlatformMessage) -> None:
        """Internal message handler dispatch."""
        if self._message_handler:
            if asyncio.iscoroutinefunction(self._message_handler):
                await self._message_handler(message)
            else:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._message_handler, message,
                )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_connected(self) -> bool:
        return self._running


class AdapterRegistry:
    """Registry for platform adapters."""

    def __init__(self) -> None:
        self._adapters: dict[PlatformType, type[PlatformAdapter]] = {}

    def register(self, platform_type: PlatformType, adapter_class: type[PlatformAdapter]) -> None:
        """Register an adapter class for a platform type."""
        self._adapters[platform_type] = adapter_class

    def get(self, platform_type: PlatformType) -> type[PlatformAdapter] | None:
        """Get adapter class for platform type."""
        return self._adapters.get(platform_type)

    def create(
        self,
        platform_type: PlatformType,
        config: dict[str, Any],
    ) -> PlatformAdapter | None:
        """Create an adapter instance."""
        adapter_class = self.get(platform_type)
        if adapter_class:
            return adapter_class(platform_type, config)
        return None

    def list_registered(self) -> list[PlatformType]:
        return list(self._adapters.keys())


# Global registry instance
adapter_registry = AdapterRegistry()


def register_adapter(
    platform_type: PlatformType, adapter_class: type[PlatformAdapter],
) -> None:
    """Register an adapter in the global registry."""
    adapter_registry.register(platform_type, adapter_class)


def create_adapter(
    platform_type: PlatformType, config: dict[str, Any],
) -> PlatformAdapter | None:
    """Create an adapter from the global registry."""
    return adapter_registry.create(platform_type, config)
