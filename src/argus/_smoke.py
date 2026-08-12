"""Smoke test pipeline — Argus.

End-to-end verification of all 10 stages:
config → workspace → memory → router → capability → orchestrator →
reflection → observability → secretvault → gateway auth.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any


def run_smoke(verbose: bool = False) -> bool:
    """Run the full pipeline smoke test. Returns True on success."""
    tmpdir = tempfile.mkdtemp(prefix="argus-smoke-")
    root = Path(tmpdir)

    def log(msg: str) -> None:
        if verbose:
            pass

    try:
        # 1. Config
        from argus.config import get_settings
        settings = get_settings()
        assert settings is not None
        log("[1] Config: OK")

        # 2. Workspace context
        from argus.workspace.context import load_workspace_context
        proj = root / "proj"
        proj.mkdir()
        (proj / "AGENTS.md").write_text("# Test Project\nRules here.")
        wc = load_workspace_context(proj)
        assert wc.files, "workspace should find context files"
        log(f"[2] Workspace: OK ({len(wc.files)} files)")

        # 3. Memory store
        from argus.memory.store import create_memory_store
        ms = create_memory_store(root / "memory.db")
        ms.add("Argus is an AI agent OS", tags=["project"])
        results = ms.search_hybrid("agent")
        assert len(results) >= 1
        log(f"[3] Memory: OK ({len(results)} hits)")

        # 4. Model router
        from argus.brain.router import ModelRouter
        router = ModelRouter(["openrouter", "nous"], "default", ["f1"])
        res = router.resolve()
        assert res.model_id == "default"
        res2 = router.resolve(explicit_override="x")
        assert res2.model_id == "x"
        log("[4] Router: OK")

        # 5. Capability engine + sandbox
        from argus.capability.engine import CapabilityEngine, CapabilityRegistry, CapabilitySpec
        from argus.runtime.sandbox import ExecutionResult, Sandbox

        def add(a: int = 0, b: int = 0, **kw: Any) -> int:
            return a + b

        registry = CapabilityRegistry()
        registry.register(
            CapabilitySpec(
                name="math.add",
                description="Add",
                parameters={"a": {"type": "integer"}, "b": {"type": "integer"}},
                returns={"type": "integer"},
            ),
            implementation=add,
        )
        engine = CapabilityEngine(registry, Sandbox())

        async def run_cap() -> ExecutionResult:
            r = await engine.execute("math.add", a=2, b=3)
            assert r.success, f"cap failed: {r.error}"
            return r

        cap = asyncio.run(run_cap())
        log(f"[5] Capability: OK (output={cap.output!r})")

        # 6. Orchestrator
        from argus.orchestrator.agent import AgentRole, AgentSpec
        from argus.orchestrator.orchestrator import OrchestrationResult, create_orchestrator

        orch = create_orchestrator(engine, registry, Sandbox())
        spec = AgentSpec(name="Worker", role=AgentRole.WORKER, capabilities=["math.add"])

        async def run_plan() -> OrchestrationResult:
            plan = await orch.create_plan("Add", [spec])
            result = await orch.execute_plan(plan)
            assert result.success, f"plan failed: {result.errors}"
            return result

        plan = asyncio.run(run_plan())
        log(f"[6] Orchestrator: OK ({len(plan.agent_results)} results)")

        # 7. Reflection
        from argus.reflection.loop import ReflectionLoop

        async def revise(out: str, critique: object) -> str:
            return "Improved " + out

        ref = asyncio.run(ReflectionLoop().run("Test", revise))
        assert ref.final_output
        log(f"[7] Reflection: OK ({ref.stopped_reason})")

        # 8. Observability
        from argus.observability.logs import create_log_collector
        from argus.observability.metrics import create_metrics_collector
        from argus.observability.store import create_obs_store
        from argus.observability.traces import create_tracer

        mc = create_metrics_collector()
        mc.increment("smoke", 3)
        assert mc.get_counter("smoke") == 3.0

        tracer = create_tracer()
        trace = tracer.start_trace("smoke")
        span = tracer.start_span("step", trace=trace)
        tracer.end_span(span)
        trace.finish()

        lc = create_log_collector()
        lc.info("smoke", trace_id=trace.trace_id)
        lc.error("smoke err")

        store = create_obs_store(root / "obs.db")
        for m in mc.snapshot():
            store.save_metric(m)
        store.save_trace(trace)
        for e in lc.query(limit=100):
            store.save_log(e)
        summary = store.get_summary()
        assert summary["metric_count"] >= 1 and summary["trace_count"] >= 1
        store.close()
        log(f"[8] Observability: OK ({summary})")

        # 9. SecretVault
        from argus.secretvault.vault import create_vault
        vault = create_vault(root / "secrets.vault", "smoke-pass")
        vault.set("api_key", "sk-smoke-1234567890abcdef")
        assert vault.get_value("api_key") == "sk-smoke-1234567890abcdef"
        vault.close()
        vault2 = create_vault(root / "secrets.vault", "smoke-pass")
        assert vault2.get_value("api_key") == "sk-smoke-1234567890abcdef"
        log("[9] SecretVault: OK")

        # 10. Gateway auth
        from argus.gateway.auth import create_auth_manager
        auth = create_auth_manager("smoke-secret")
        token = auth.create_token("agent-1", scopes=["read"])
        data = auth.verify_token(token)
        assert data is not None and data.sub == "agent-1"
        log("[10] Gateway Auth: OK")

        return True
    except Exception as e:  # pragma: no cover
        if verbose:
            pass
        return False


if __name__ == "__main__":  # pragma: no cover
    ok = run_smoke(verbose=True)
    raise SystemExit(0 if ok else 1)
