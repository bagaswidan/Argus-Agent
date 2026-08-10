"""Configuration system — Argus Core Foundation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"  # json | console
    output: str = "stdout"  # stdout | stderr | file
    file_path: Path | None = None
    json_fields: list[str] = Field(default_factory=lambda: ["timestamp", "level", "logger", "message"])


class EventBusConfig(BaseModel):
    """Event bus configuration."""

    max_queue_size: int = 10000
    worker_count: int = 4
    enable_priority: bool = True
    dead_letter_enabled: bool = True
    dead_letter_max_size: int = 1000


class SchedulerConfig(BaseModel):
    """Scheduler configuration."""

    max_workers: int = 8
    default_timeout_s: float = 30.0
    enable_priority_queue: bool = True
    checkpoint_interval_s: float = 60.0


class OrchestratorConfig(BaseModel):
    """Orchestrator configuration."""

    max_concurrent_workflows: int = 100
    workflow_timeout_s: float = 300.0
    retry_max_attempts: int = 3
    retry_base_delay_s: float = 1.0


class CapabilityConfig(BaseModel):
    """Capability engine configuration."""

    registry_path: Path | None = None
    enable_ranking: bool = True
    default_trust_score: float = 0.5
    ranking_weights: dict[str, float] = Field(default_factory=lambda: {
        "trust": 0.3,
        "reliability": 0.25,
        "latency": 0.2,
        "cost": 0.15,
        "resource_usage": 0.1,
    })


class ExtensionConfig(BaseModel):
    """Extension system configuration."""

    extensions_dir: Path | None = None
    auto_load: bool = False
    validate_on_load: bool = True
    sandbox_enabled: bool = False  # Phase 2+


class SecurityConfig(BaseModel):
    """Security configuration."""

    permission_engine_enabled: bool = True
    policy_engine_enabled: bool = True
    default_deny: bool = True  # Zero trust
    audit_enabled: bool = True


class MemoryConfig(BaseModel):
    """Memory configuration."""

    context_ttl_s: int = 3600
    session_ttl_s: int = 86400
    max_context_size: int = 10000
    max_session_size: int = 50000


class BrainConfig(BaseModel):
    """Brain configuration."""

    thinking_modes: list[str] = Field(default_factory=lambda: ["fast", "balanced", "deep"])
    default_thinking_mode: str = "balanced"
    max_planning_depth: int = 10
    max_replan_attempts: int = 3


class ArgusSettings(BaseSettings):
    """Root settings — all configuration loaded from env/file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_prefix="ARGUS_",
        case_sensitive=False,
        extra="ignore",
    )

    # Core
    app_name: str = "argus"
    version: str = "0.1.0"
    environment: str = "development"  # development | staging | production
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".argus")

    # Sub-configs
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    event_bus: EventBusConfig = Field(default_factory=EventBusConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    capability: CapabilityConfig = Field(default_factory=CapabilityConfig)
    extension: ExtensionConfig = Field(default_factory=ExtensionConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    brain: BrainConfig = Field(default_factory=BrainConfig)

    def get_data_dir(self) -> Path:
        """Get resolved data directory."""
        path = self.data_dir.expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


# Global settings instance
_settings: ArgusSettings | None = None


def get_settings() -> ArgusSettings:
    """Get global settings (singleton)."""
    global _settings
    if _settings is None:
        _settings = ArgusSettings()
    return _settings


def reset_settings() -> None:
    """Reset settings (for testing)."""
    global _settings
    _settings = None