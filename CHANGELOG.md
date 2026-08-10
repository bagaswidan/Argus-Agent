# Changelog

All notable changes go here, in the style of [Keep a Changelog](https://keepachangelog.com/). The project follows [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Refinements: Streaming Manager (`runtime/streaming.py`), Runtime Monitor (`runtime/monitor.py`), Intent Parser + Problem Solver (`brain/intent.py`, `brain/solver.py`), Knowledge Fabric (`knowledge/`), Verification Stage (`verification/`) — 448 tests total
- Phase 6 — Dashboard: `argus dashboard` (stdlib HTTP server, dark/bright themes, metrics/traces/logs view)
- Phase 9 — Deployment: multi-stage `Dockerfile`, `compose.yaml` (argus + dashboard services), `.dockerignore`
- Phase 11 — Self Evolution: `argus curator` (usage tracker, archive/restore, failure lessons)
- Desktop UI mockup (Cursor/Hermes-style) with dark and bright themes — HTML prototype in `examples/desktop/`
- Branding module (`src/argus/branding.py`) with the Panoptes eye logo, vision, and constitution from the engineering spec
- `argus logo`, `argus ask`, `argus dashboard`, `argus curator` CLI commands; `argus version` prints the full logo
- Cross-platform CI workflow (Linux/Windows/macOS) via GitHub Actions
- Full English documentation: README, ARCHITECTURE, CONTRIBUTING, CHANGELOG, SECURITY, CODE_OF_CONDUCT

## [1.1.0] - 2026-08-10

### Added
- `contracts/` — typed inter-module messages (Request, Decision, CapabilityRequest, FailureObject) with validation
- `security/` — zero-trust permission engine, default-deny, glob resource matching
- `extension/` — plugin architecture: manifests, RPC contract (initialize/execute/health/configure/shutdown), lifecycle manager
- `brain/planning.py` — dependency-graph planning with cycle detection and critical-path estimation
- `runtime/` — scheduler, state manager (workflow FSM), transaction manager with recovery suggestions, lock manager, workflow engine with pause/resume and checkpoints
- OpenAI-compatible provider client for OmniRoute/OpenRouter-style backends

### Fixed
- Combo routing in OmniRoute that pointed at a nonexistent connection (503 "No credentials") — verified against the live service

## [1.0.0] - 2026-08-09

### Added
- First publishable release: 256 tests passing, smoke test pipeline (10 stages)
- Model router with fallback chains
- Capability engine with registry, retry, and cost tracking
- Sandbox runtime (THREAD/SUBPROCESS), memory store (SQLite+FTS5), multi-agent orchestrator
- Reflection loop, gateway (auth + adapters + server), observability (metrics/traces/logs), secret vault (Fernet)
- CLI: `argus version | status | smoke`
- Packaging: wheel `py3-none-any`, Python >= 3.12, MIT license
