"""Test Event Bus — Argus Core Foundation."""
from __future__ import annotations

import asyncio

import pytest

from argus.common.events import Event, EventBus, EventPriority, Subscription


class TestEvent:
    def test_event_creation(self):
        evt = Event(type="test.event", payload={"key": "value"}, source="test")
        assert evt.type == "test.event"
        assert evt.payload == {"key": "value"}
        assert evt.source == "test"
        assert evt.correlation_id is not None
        assert evt.timestamp is not None

    def test_event_with_correlation_id(self):
        evt = Event(type="test", payload={}, correlation_id="corr-123")
        assert evt.correlation_id == "corr-123"


class TestEventPriority:
    def test_priority_ordering(self):
        assert EventPriority.LOW < EventPriority.NORMAL
        assert EventPriority.NORMAL < EventPriority.HIGH
        assert EventPriority.HIGH < EventPriority.CRITICAL


@pytest.fixture
def event_bus():
    return EventBus(max_queue_size=100, worker_count=2)


class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, event_bus):
        received = []

        def handler(evt: Event):
            received.append(evt)

        sub = event_bus.subscribe("test.event", handler)
        await event_bus.publish(Event(type="test.event", payload={"data": 123}))
        await event_bus.flush()

        assert len(received) == 1
        assert received[0].payload == {"data": 123}
        sub.unsubscribe()

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, event_bus):
        received1 = []
        received2 = []

        def h1(evt): received1.append(evt)
        def h2(evt): received2.append(evt)

        event_bus.subscribe("multi.event", h1)
        event_bus.subscribe("multi.event", h2)

        await event_bus.publish(Event(type="multi.event", payload={}))
        await event_bus.flush()

        assert len(received1) == 1
        assert len(received2) == 1

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self, event_bus):
        received = []

        def handler(evt: Event):
            received.append(evt.type)

        event_bus.subscribe("test.*", handler)
        await event_bus.publish(Event(type="test.a", payload={}))
        await event_bus.publish(Event(type="test.b", payload={}))
        await event_bus.publish(Event(type="other.c", payload={}))
        await event_bus.flush()

        assert received == ["test.a", "test.b"]

    @pytest.mark.asyncio
    async def test_priority_delivery(self, event_bus):
        order = []

        def low(evt): order.append("low")
        def normal(evt): order.append("normal")
        def high(evt): order.append("high")
        def critical(evt): order.append("critical")

        event_bus.subscribe("priority.test", low, priority=EventPriority.LOW)
        event_bus.subscribe("priority.test", normal, priority=EventPriority.NORMAL)
        event_bus.subscribe("priority.test", high, priority=EventPriority.HIGH)
        event_bus.subscribe("priority.test", critical, priority=EventPriority.CRITICAL)

        await event_bus.publish(Event(type="priority.test", payload={}))
        await event_bus.flush()

        assert order == ["critical", "high", "normal", "low"]

    @pytest.mark.asyncio
    async def test_async_handler(self, event_bus):
        received = []

        async def handler(evt: Event):
            await asyncio.sleep(0.01)
            received.append(evt.payload["value"])

        event_bus.subscribe("async.test", handler)
        await event_bus.publish(Event(type="async.test", payload={"value": 42}))
        await event_bus.flush()

        assert received == [42]

    @pytest.mark.asyncio
    async def test_handler_exception_isolation(self, event_bus):
        received = []

        def bad_handler(evt): raise ValueError("boom")
        def good_handler(evt): received.append("ok")

        event_bus.subscribe("error.test", bad_handler)
        event_bus.subscribe("error.test", good_handler)

        await event_bus.publish(Event(type="error.test", payload={}))
        await event_bus.flush()

        assert received == ["ok"]

    @pytest.mark.asyncio
    async def test_unsubscribe(self, event_bus):
        received = []

        def handler(evt): received.append(1)

        sub = event_bus.subscribe("unsub.test", handler)
        await event_bus.publish(Event(type="unsub.test", payload={}))
        await event_bus.flush()
        assert len(received) == 1

        sub.unsubscribe()
        await event_bus.publish(Event(type="unsub.test", payload={}))
        await event_bus.flush()
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_dead_letter_queue(self, event_bus):
        await event_bus.publish(Event(type="no.subscriber", payload={}))
        await event_bus.flush()

        dead = event_bus.get_dead_letters()
        assert len(dead) == 1
        assert dead[0].type == "no.subscriber"

    @pytest.mark.asyncio
    async def test_queue_overflow(self, event_bus):
        for i in range(150):
            await event_bus.publish(Event(type=f"overflow.{i}", payload={}))
        await event_bus.flush()

    @pytest.mark.asyncio
    async def test_flush_waits_for_handlers(self, event_bus):
        done = asyncio.Event()

        async def slow_handler(evt):
            await asyncio.sleep(0.05)
            done.set()

        event_bus.subscribe("slow.test", slow_handler)
        await event_bus.publish(Event(type="slow.test", payload={}))
        await event_bus.flush()
        assert done.is_set()


class TestSubscription:
    def test_subscription_context_manager(self, event_bus):
        received = []

        def handler(evt): received.append(1)

        with event_bus.subscribe("ctx.test", handler) as sub:
            assert isinstance(sub, Subscription)
        # auto unsubscribed — publish after context exit
        asyncio.run(event_bus.publish(Event(type="ctx.test", payload={})))
        asyncio.run(event_bus.flush())
        assert len(received) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
