# Blueprint Compliance

Where the code stands against the Engineering Specification v1.0 (4 parts),
as of v1.1.0. All 11 roadmap phases are now implemented.

## Roadmap status (PART 1 §10)

| Phase | Component | Status |
|---|---|---|
| 1 | Foundation (config, common, workspace, memory) | done |
| 2 | Runtime (sandbox, scheduler, state, tx, lock, workflow) | done |
| 3 | Extension Architecture (manifest, RPC, lifecycle) | done |
| 4 | Capability Engine | done |
| 5 | Security (zero-trust) | done |
| 6 | **Dashboard** (`argus dashboard`, web UI, dark/bright) | done |
| 7 | Planning & Decision | done |
| 8 | Multi-Agent | done |
| 9 | **Deployment** (Dockerfile, compose.yaml) | done |
| 10 | Testing (387 tests, smoke pipeline) | done |
| 11 | **Self Evolution** (`argus curator`, usage tracker, lessons) | done |

## Covered

### Part 1 — Architecture & principles
- Vision and Constitution (8 principles) are implemented as the branding
  module's `VISION` / `CONSTITUTION` constants and enforced in code where it
  matters (default-deny security, evidence-first decisions).

### Part 2 — Brain
| Component | Where | Status |
|---|---|---|
| Goal Engine | `brain/goal.py` | done |
| Planning Engine | `brain/planning.py` | done — dependency graph, cycle detection, critical path |
| Decision Engine | `brain/decision.py` | done — decisions always recorded |
| Reflection Engine | `reflection/` | done |
| Thinking Selector | `brain/thinking.py` | done — 7 modes |
| Intent Parser | folded into Goal Engine input | partial |
| Problem Solver | recovery via `runtime/transaction.py` | partial |

### Part 3 — Runtime
| Component | Where | Status |
|---|---|---|
| Orchestrator | `orchestrator/` | done |
| Event Bus | `common/events.py` | done |
| Scheduler | `runtime/scheduler.py` | done |
| State Manager | `runtime/state.py` | done |
| Transaction + Recovery | `runtime/transaction.py` | done |
| Lock Manager | `runtime/lock.py` | done |
| Workflow Engine | `runtime/workflow.py` | done |
| Sandbox | `runtime/sandbox.py` | done |
| Streaming Manager | — | not yet |
| Runtime Monitor | — | not yet |

### Part 4 — Capability & Extension
| Component | Where | Status |
|---|---|---|
| Capability Engine | `capability/engine.py` | done |
| Extension Manifest | `extension/manifest.py` | done |
| Extension RPC Contract | `extension/rpc.py` | done |
| Extension Lifecycle | `extension/manager.py` | done |
| Security Engine | `security/engine.py` | done |
| Contracts | `contracts/types.py` | done |

## Remaining gaps (future releases)

None blocking. All roadmap phases are done, and the refinement items from
the spec are now implemented too:

- **Streaming Manager** — `runtime/streaming.py` (async chunked output, cancellation, backpressure)
- **Runtime Monitor** — `runtime/monitor.py` (task lifecycle tracking, summary snapshots)
- **Intent Parser** — `brain/intent.py` (rule-based intent + entity extraction)
- **Problem Solver** — `brain/solver.py` (failure classification + recovery suggestions)
- **Knowledge Fabric** — `knowledge/` (validated facts with source + confidence)
- **Verification Stage** — `verification/` (pluggable checks: empty, error flag, secret leak, success)

Total: 448 tests passing across 38 test files.
