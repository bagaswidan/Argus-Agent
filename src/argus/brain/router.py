"""Model Router — Argus.

Resolves the active provider/model with an ordered fallback chain.
Ordering contract:
    1. explicit override
    2. config default + fallbacks
    3. provider resolution (use first provider that has the model)
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelResolution:
    provider_id: str
    model_id: str
    attempt: int
    total_candidates: int
    overrides: tuple[str, ...]
    available_providers: tuple[str, ...]
    available_models: tuple[str, ...]


@dataclass(frozen=True)
class ModelCandidate:
    provider_id: str
    model_id: str


class ModelRouter:
    def __init__(
        self,
        providers: Sequence[str],
        default_model: str,
        fallback_models: Sequence[str] | None = None,
        explicit_provider: str | None = None,
    ) -> None:
        self.providers = tuple(providers)
        self.default_model = default_model
        self.fallback_models = tuple(fallback_models or [])
        self.explicit_provider = explicit_provider

    def resolve(
        self,
        explicit_override: str | None = None,
        allowed_providers: Iterable[str] | None = None,
    ) -> ModelResolution:
        candidates = self._build_candidates(explicit_override)
        allowed_set = set(allowed_providers) if allowed_providers else None
        providers = tuple(
            p for p in candidates if (allowed_set is None or p.provider_id in allowed_set)
        )
        chosen = providers[0] if providers else None
        return ModelResolution(
            provider_id=chosen.provider_id if chosen else self.providers[0],
            model_id=chosen.model_id if chosen else self.default_model,
            attempt=1,
            total_candidates=len(candidates),
            overrides=tuple(
                [explicit_override] if explicit_override and chosen else [],
            ),
            available_providers=self.providers,
            available_models=tuple(sorted({c.model_id for c in candidates})),
        )

    def _build_candidates(self, explicit_override: str | None) -> list[ModelCandidate]:
        ordered = []
        if explicit_override:
            # For explicit override, use explicit_provider or first provider
            provider_for_override = self.explicit_provider or self.providers[0]
            ordered.append(
                ModelCandidate(provider_id=provider_for_override, model_id=explicit_override),
            )
        # Default model for each provider
        for provider in self.providers:
            ordered.append(ModelCandidate(provider_id=provider, model_id=self.default_model))
        # Fallback models for each provider
        for provider in self.providers:
            for model in self.fallback_models:
                ordered.append(ModelCandidate(provider_id=provider, model_id=model))
        return ordered
