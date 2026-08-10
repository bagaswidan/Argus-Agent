# Argus

An AI agent framework that keeps its head down and does the work. Built around a simple idea from the Greek myth: Argus Panoptes, the hundred-eyed giant who never quite slept, always watching. That's the vibe — an agent that observes everything, keeps receipts, and doesn't guess.

Under the hood it's a modular Python framework. Model routing, capability execution, sandboxed runtime, memory, multi-agent orchestration, reflection, a gateway, observability, and a secret vault. Pick what you need, leave the rest.

Current state: 369 tests, all passing, on Python 3.12+.

## What's inside

| Module | What it does |
|---|---|
| `brain/` | Model router, provider client, thinking modes, goal engine, decision memory, planning |
| `capability/` | The execution unit — registry, retry policy, cost tracking, sandboxed runs |
| `runtime/` | Sandbox, scheduler, state machine, transactions, locks, workflow engine |
| `security/` | Zero-trust permission checks before anything executes |
| `extension/` | Plug-in architecture: manifests, RPC contract, lifecycle manager |
| `contracts/` | Typed objects for inter-module messages (no more loose dicts) |
| `dashboard/` | Web dashboard: summary cards, traces, logs, dark/bright themes |
| `curator/` | Self-evolution: usage tracking, archiving, failure lessons |
| `verification/` | Pipeline checks before responding: empty, error, secret-leak, success |
| `knowledge/` | Validated knowledge store with source + confidence |
| `memory/` | SQLite + FTS5 store with hybrid search |
| `reflection/` | A critic that reviews its own work before calling it done |
| `gateway/` | Auth, platform adapters, HTTP server |
| `observability/` | Metrics, traces, structured logs, all persisted to SQLite |
| `secretvault/` | Fernet-encrypted secrets with key rotation |

The whole thing is documented against an engineering spec — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design rationale and how the pieces talk to each other.

## Install

```bash
pip install argus
```

Or from source:

```bash
git clone https://github.com/<your-user>/argus.git
cd argus
pip install -e .
```

Needs Python 3.12 or newer. No GPU, no Docker, no external services required. SQLite is built into the stdlib, and everything else is pure Python.

## Quick start

```bash
argus version        # prints the logo and version
argus status         # system summary
argus smoke          # runs the 10-stage self-check
argus ask "..."      # sends a prompt to an LLM (OmniRoute-compatible)
argus logo --render  # renders the Panoptes eye as a JPEG
```

If you're writing code, the entry points are in `src/argus/`. A typical flow looks like:

```python
from argus.capability.engine import create_capability_engine

engine = create_capability_engine()
result = engine.execute("math.add", {"a": 2, "b": 3})
print(result.output)  # "5"
```

## How it's tested

`scripts/run_tests.sh` runs the suite with a clean environment — no stray env vars, UTC timezone, temp HOME. That's how CI runs it too.

```bash
scripts/run_tests.sh          # everything
scripts/run_tests.sh tests/unit/brain/   # one directory
```

Tests live next to the code: `tests/unit/<module>/test_<module>.py`. We write them first, then the code. The flaky-policy is simple: if a test passes on retry, it's still a bug to fix, not something to ignore.

## Project layout

```
src/argus/
├── brain/         routing, provider, thinking, goals, decisions, planning
├── capability/    execution engine
├── common/        DI container, errors, event bus, logging
├── config/        settings via pydantic
├── contracts/     typed inter-module messages
├── extension/     plugin manifests + lifecycle
├── gateway/       auth, adapters, server
├── memory/        SQLite + FTS5
├── observability/ metrics, traces, logs
├── orchestrator/  multi-agent coordination
├── reflection/    self-critique loop
├── runtime/       sandbox, scheduler, state, tx, locks, workflows
├── secretvault/   encrypted secrets
├── security/      permission engine
└── workspace/     context loading
```

## Contributing

Pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first — it covers the test-first rule, the flaky policy, and why we don't merge change-detector tests.

Security issues: check [SECURITY.md](SECURITY.md) before filing anything public.

## License

MIT. See [LICENSE](LICENSE).
