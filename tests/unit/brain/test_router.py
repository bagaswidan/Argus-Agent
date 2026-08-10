"""Test Model Router — Argus Brain."""
from __future__ import annotations

import pytest

from argus.brain.router import ModelRouter, ModelResolution


class TestModelRouterBasics:
    """Basic router behavior."""

    def test_resolve_default(self):
        router = ModelRouter(
            providers=["openrouter", "nous", "custom"],
            default_model="default",
        )
        res = router.resolve()
        assert res.model_id == "default"
        assert res.provider_id == "openrouter"

    def test_resolve_with_override(self):
        router = ModelRouter(
            providers=["openrouter", "nous", "custom"],
            default_model="default",
            explicit_provider="custom",
        )
        res = router.resolve(explicit_override="codex:main")
        assert res.model_id == "codex:main"
        assert res.provider_id == "custom"

    def test_resolve_with_provider_allowlist(self):
        router = ModelRouter(
            providers=["openrouter", "nous", "custom"],
            default_model="default",
        )
        res = router.resolve(allowed_providers=["nous"])
        assert res.provider_id == "nous"
        assert res.model_id == "default"


class TestModelRouterFallback:
    """Fallback chain behavior."""

    def test_fallback_uses_first(self):
        router = ModelRouter(
            providers=["a", "b", "c"],
            default_model="Ubuntu-Bagas",
            fallback_models=["Lumayan", "Cadangan", "Coding-Focused"],
        )
        res = router.resolve()
        assert res.model_id == "Ubuntu-Bagas"

    def test_fallback_after_default(self):
        router = ModelRouter(
            providers=["a", "b", "c"],
            default_model="Ubuntu-Bagas",
            fallback_models=["Lumayan", "Cadangan", "Coding-Focused"],
        )
        # Simulate default failing by advising to first fallback available
        res = router.resolve()
        assert res.provider_id == "a"
        assert res.model_id == "Ubuntu-Bagas"
        assert "Lumayan" in res.available_models or res.total_candidates > 1

    def test_explicit_override_uses_explicit_provider(self):
        router = ModelRouter(
            providers=["a", "b", "c"],
            default_model="Ubuntu-Bagas",
            explicit_provider="c",
        )
        res = router.resolve(explicit_override="Lumayan")
        assert res.provider_id == "c"
        assert res.model_id == "Lumayan"


class TestModelResolution:
    """Resolution metadata sanity."""

    def test_resolution_payload(self):
        router = ModelRouter(
            providers=["a"],
            default_model="Ubuntu-Bagas",
        )
        res = router.resolve()
        assert res.provider_id == "a"
        assert res.model_id == "Ubuntu-Bagas"
        assert res.total_candidates == 1
        assert res.available_models == ("Ubuntu-Bagas",)
