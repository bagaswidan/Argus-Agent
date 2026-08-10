# Architecture

This document explains how Argus is put together and why it's shaped the way it is. It follows the Engineering Specification v1.0 that the project was built against — the short version is: capabilities are the unit of work, everything else exists to route, secure, and observe them.

## The pipeline

A request doesn't flow through the whole stack on every call, but when it does, it looks like this:

```
Communication → Brain → Goal → Planning → Decision → Capability
    → Security → Runtime → Verification → Reflection → Knowledge → Response
```

Two rules hold it together:

1. **The brain doesn't call tools directly.** It produces a `CapabilityRequest`. Something else executes it. That split is what keeps the reasoning loop testable without a real backend attached.
2. **Everything that runs is a capability.** If it isn't a capability, it's infrastructure around capabilities — routing, permission checks, scheduling, observability.

## Modules

### brain/

Model selection and reasoning state. `router.py` resolves a model request through a fallback chain: explicit override, then config default, then provider defaults. `provider.py` is a small OpenAI-compatible client that works with OmniRoute, OpenRouter, or anything speaking that dialect — it sends `stream: false` explicitly because OmniRoute defaults to SSE. `thinking.py` picks a thinking mode, `goal.py` decomposes a goal into steps, `decision.py` keeps a record of choices with confidence scores, and `planning.py` builds dependency graphs with cycle detection and critical-path estimation.

### capability/

The registry holds capability specs — id, input/output contracts, version, permissions. `engine.py` resolves a request by registry lookup, applies policy, respects retry limits, and tracks cost. Sandboxed execution happens downstream in `runtime/`, not here.

### runtime/

Execution infrastructure:

- `sandbox.py` — isolates capability calls. Default mode is THREAD because it's cross-platform; SUBPROCESS works when the callable is picklable and top-level.
- `scheduler.py` — an async task queue with priorities and timeouts.
- `state.py` — workflow state machine (created → queued → running → paused → … → completed/failed/archived) with illegal-transition checks.
- `transaction.py` — Begin → Checkpoint → Commit → Rollback, plus recovery-strategy suggestions (retry, resume, fallback, abort, replan) based on the error text.
- `lock.py` — prevents the same capability running twice.
- `workflow.py` — multi-step runs with pause/resume and checkpoint snapshots.

### security/

Default-deny permission engine. You grant access explicitly (`engine.allow("user1", "deploy.*")`), everything else is refused. Supports glob resources and first-match-wins ordering, so `deny` beats a wildcard `allow` if it comes first.

### extension/

Plugins declare a manifest (YAML or dict), load through the manager, and speak a fixed RPC contract: initialize, execute, health, configure, shutdown. Each call returns a response object with status, evidence, and optional error — the same shape regardless of what the extension actually does. If one extension crashes, the manager keeps the others running.

### contracts/

Typed dataclasses — `Request`, `Decision`, `CapabilityRequest`, `ExecutionResultContract`, `FailureObject` — with a `validate_contract()` helper. Modules import these instead of passing dicts around, which means a typo in a key name shows up at import time, not at 2am in production.

### memory/

SQLite-backed store with FTS5 for text search and a hybrid path (FTS + vector metadata) for ranking. Multi-word queries get rewritten with prefix tokens (`term*`) so partial matches work — that was a real bug, not a design choice. See `search_fts`.

### reflection/

A critic reviews execution results across seven categories (completeness, correctness, security, evidence, style, cost, consistency), each with severity. `loop.py` iterates: run, critique, revise, re-run — bounded by max iterations.

### gateway/

`auth.py` issues and verifies tokens (JWT or simple HMAC). `adapters.py` is the platform adapter ABC. `server.py` is an aiohttp-based HTTP server, but aiohttp is optional — if it's missing, the gateway reports it and the rest of the framework keeps working.

### observability/

Metrics (counter, gauge, histogram), traces, and structured logs, all persisted to a SQLite store. Percentiles use nearest-rank. `store.py` is shared by all three.

### secretvault/

Fernet (AES-128) encryption with PBKDF2 key derivation. Salt and iteration count are stored in the vault file header so a file can be opened without external config. Key rotation supported.

## Cross-platform notes

The wheel is `py3-none-any` and there are no platform-specific imports in `src/` — no `fcntl`, no `msvcrt`, no `os.fork`. SQLite is stdlib. aiohttp is optional. That's deliberate: Argus was tested on Linux, but nothing in the code stops it running on Windows or macOS. The THREAD sandbox mode exists partly for that reason.

## Testing philosophy

Tests assert relationships, not snapshots. We don't write tests that fail when a model list grows or a version number bumps. If a test reads a source file to check "structure", it's rejected in review — behavior only. Every module has a `create_*` factory, so tests can build engines with defaults instead of reaching into internals.
