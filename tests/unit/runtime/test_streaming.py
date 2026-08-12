"""Test Streaming Manager — Argus (Refinement 1)."""
from __future__ import annotations

import asyncio

import pytest

from argus.runtime.streaming import (
    collect_stream,
    create_streaming_manager,
)


class TestStreamingManager:
    @pytest.mark.asyncio
    async def test_stream_chunks_in_order(self):
        mgr = create_streaming_manager()

        async def producer(emit):
            await emit("hello ")
            await emit("world")

        chunks = [c.data async for c in mgr.stream(producer)]
        assert chunks == ["hello ", "world", ""]

    @pytest.mark.asyncio
    async def test_done_flag_on_last_chunk(self):
        mgr = create_streaming_manager()

        async def producer(emit):
            await emit("only")

        last = None
        async for c in mgr.stream(producer):
            last = c
        assert last.done is True

    @pytest.mark.asyncio
    async def test_sequence_numbers(self):
        mgr = create_streaming_manager()

        async def producer(emit):
            await emit("a")
            await emit("b")
            await emit("c")

        seqs = [c.sequence async for c in mgr.stream(producer) if c.data]
        assert seqs == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_error_propagates(self):
        mgr = create_streaming_manager()

        async def producer(emit):
            await emit("before")
            raise RuntimeError("boom")

        result = await collect_stream(mgr, producer)
        assert result.error == "boom"
        assert result.full_text == "before"

    @pytest.mark.asyncio
    async def test_cancel_raises_in_producer(self):
        mgr = create_streaming_manager()
        entered = asyncio.Event()

        async def producer(emit):
            await emit("start")
            entered.set()
            # keep emitting until the manager cancels us
            while True:
                await asyncio.sleep(0.01)
                await emit("tick")

        # cancel from outside after first chunk
        async def cancel_after_first():
            async for _ in mgr.stream(producer, stream_id="cx"):
                assert mgr.cancel("cx") is True
                break

        await cancel_after_first()
        await asyncio.sleep(0.02)
        assert mgr.is_active("cx") is False

    @pytest.mark.asyncio
    async def test_is_active_and_count(self):
        mgr = create_streaming_manager()

        async def producer(emit):
            await emit("x")

        async for _ in mgr.stream(producer, stream_id="s1"):
            assert mgr.is_active("s1") is True
            assert mgr.active_count() == 1
        assert mgr.is_active("s1") is False
        assert mgr.active_count() == 0

    @pytest.mark.asyncio
    async def test_collect_stream_aggregates(self):
        mgr = create_streaming_manager()

        async def producer(emit):
            await emit("one ")
            await emit("two ")
            await emit("three")

        result = await collect_stream(mgr, producer)
        assert result.full_text == "one two three"
        assert result.chunk_count == 3
        assert result.error is None
        assert result.cancelled is False
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_cancel_inactive_returns_false(self):
        mgr = create_streaming_manager()
        assert mgr.cancel("nope") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
