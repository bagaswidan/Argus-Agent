"""Communication — Argus Multi-Agent Orchestrator.

Message bus for inter-agent communication and event propagation.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass
class AgentMessage:
    """Message between agents."""

    id: str = field(default_factory=lambda: str(uuid4()))
    from_agent: str = ""
    to_agent: str = ""  # Empty = broadcast
    message_type: str = "task"  # task, result, status, control
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str = ""  # For request-response pairing

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message_type": self.message_type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
        }


class MessageBus:
    """Async message bus for agent communication."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, list[asyncio.Queue[AgentMessage]]] = defaultdict(list)
        self._broadcast_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._history: list[AgentMessage] = []
        self._max_history = 1000

    async def subscribe(self, agent_id: str) -> asyncio.Queue[AgentMessage]:
        """Subscribe an agent to receive messages."""
        queue: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._subscriptions[agent_id].append(queue)
        return queue

    def unsubscribe(self, agent_id: str, queue: asyncio.Queue[AgentMessage]) -> None:
        """Unsubscribe an agent."""
        if agent_id in self._subscriptions:
            self._subscriptions[agent_id].remove(queue)

    async def send(self, message: AgentMessage) -> None:
        """Send a message to a specific agent or broadcast."""
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        if message.to_agent:
            # Direct message – iterate over a snapshot to avoid
            # concurrent modification if unsubscribe runs in another task.
            queues_snapshot = list(self._subscriptions.get(message.to_agent, []))
            for queue in queues_snapshot:
                await queue.put(message)
        else:
            # Broadcast to all – snapshot both outer dict and inner lists.
            for agent_queues in list(self._subscriptions.values()):
                for queue in list(agent_queues):
                    await queue.put(message)

    async def broadcast(self, message: AgentMessage) -> None:
        """Broadcast a message to all subscribers."""
        message.to_agent = ""
        await self.send(message)

    async def request_response(
        self,
        from_agent: str,
        to_agent: str,
        message_type: str,
        payload: dict[str, Any],
        timeout: float = 30.0,
    ) -> AgentMessage | None:
        """Send a request and wait for response."""
        correlation_id = str(uuid4())
        request = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            payload=payload,
            correlation_id=correlation_id,
        )

        # Subscribe to response
        response_queue = await self.subscribe(f"{from_agent}:response:{correlation_id}")

        await self.send(request)

        try:
            response = await asyncio.wait_for(response_queue.get(), timeout=timeout)
            return response
        except TimeoutError:
            return None
        finally:
            self.unsubscribe(f"{from_agent}:response:{correlation_id}", response_queue)

    def get_history(
        self, agent_id: str | None = None, limit: int = 100,
    ) -> list[AgentMessage]:
        """Get message history."""
        if agent_id:
            return [
                m
                for m in self._history
                if m.from_agent == agent_id or m.to_agent == agent_id or m.to_agent == ""
            ][-limit:]
        return self._history[-limit:]


# Global message bus instance
_message_bus: MessageBus | None = None


def get_message_bus() -> MessageBus:
    """Get or create the global message bus."""
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus
