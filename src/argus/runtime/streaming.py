"""Streaming Manager — Argus Runtime (Refinement 1).

Turns a long-running capability into an async stream of chunks so callers
see partial output as it's produced, instead of waiting for the whole
result. Supports backpressure, cancellation, and per-chunk metadata.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Optional


class StreamCancelled(Exception):
    """Raised inside the producer when the consumer cancels the stream."""


@dataclass
class StreamChunk:
    """One piece of streamed output."""

    stream_id: str
    data: str
    sequence: int = 0
    done: bool = False
    error: Optional[str] = None
    at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "data": self.data,
            "sequence": self.sequence,
            "done": self.done,
            "error": self.error,
            "at": self.at,
        }


@dataclass
class StreamResult:
    """Aggregate result after a stream finishes."""

    stream_id: str
    full_text: str = ""
    chunk_count: int = 0
    duration_ms: int = 0
    cancelled: bool = False
    error: Optional[str] = None


class StreamingManager:
    """Manages concurrent streams from async producers."""

    def __init__(self) -> None:
        self._streams: dict[str, asyncio.Queue] = {}
        self._events: dict[str, asyncio.Event] = {}
        self._next_seq: dict[str, int] = {}

    async def stream(
        self,
        producer: Callable[[Callable[[str], Awaitable[None]]], Awaitable[Any]],
        stream_id: Optional[str] = None,
        buffer: int = 32,
    ) -> AsyncIterator[StreamChunk]:
        """Run a producer that calls ``emit(chunk_text)``; yield chunks.

        Example:
            async def run(emit):
                await emit("part one ")
                await emit("part two")

            async for chunk in manager.stream(run):
                print(chunk.data)
        """
        sid = stream_id or uuid.uuid4().hex[:12]
        queue: asyncio.Queue = asyncio.Queue(maxsize=buffer)
        self._streams[sid] = queue
        self._next_seq[sid] = 0
        cancel_event = asyncio.Event()
        self._events[sid] = cancel_event

        start = time.time()

        async def emit(text: str) -> None:
            if cancel_event.is_set():
                raise StreamCancelled(f"stream {sid} cancelled")
            seq = self._next_seq[sid]
            self._next_seq[sid] += 1
            await queue.put(StreamChunk(stream_id=sid, data=text, sequence=seq))

        async def producer_runner() -> None:
            try:
                await producer(emit)
                await queue.put(StreamChunk(stream_id=sid, data="", done=True))
            except asyncio.CancelledError:
                await queue.put(StreamChunk(stream_id=sid, data="", done=True, error="cancelled"))
            except Exception as exc:  # noqa: BLE001
                await queue.put(StreamChunk(stream_id=sid, data="", done=True, error=str(exc)))

        task = asyncio.create_task(producer_runner())
        try:
            while True:
                chunk = await queue.get()
                yield chunk
                if chunk.done:
                    break
        finally:
            task.cancel()
            cancel_event.set()
            self._streams.pop(sid, None)
            self._events.pop(sid, None)

    def is_active(self, stream_id: str) -> bool:
        return stream_id in self._streams

    def active_count(self) -> int:
        return len(self._streams)

    def cancel(self, stream_id: str) -> bool:
        """Request cancellation of a stream. Returns True if it was active."""
        event = self._events.get(stream_id)
        if event is None:
            return False
        event.set()
        return True


async def collect_stream(
    manager: StreamingManager,
    producer: Callable[[Callable[[str], Awaitable[None]]], Awaitable[Any]],
    stream_id: Optional[str] = None,
) -> StreamResult:
    """Convenience: run a stream to completion and aggregate it."""
    start = time.time()
    full: list[str] = []
    count = 0
    cancelled = False
    error: Optional[str] = None
    sid = stream_id or uuid.uuid4().hex[:12]
    async for chunk in manager.stream(producer, stream_id=sid):
        if chunk.data:
            full.append(chunk.data)
            count += 1
        if chunk.error:
            if chunk.error == "cancelled":
                cancelled = True
            else:
                error = chunk.error
    return StreamResult(
        stream_id=sid,
        full_text="".join(full),
        chunk_count=count,
        duration_ms=int((time.time() - start) * 1000),
        cancelled=cancelled,
        error=error,
    )


def create_streaming_manager() -> StreamingManager:
    return StreamingManager()
