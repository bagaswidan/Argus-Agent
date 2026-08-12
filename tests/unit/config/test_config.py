"""Test configuration system — Argus Core Foundation."""
from __future__ import annotations

import pytest

from argus.config import (
    ArgusSettings,
    BrainConfig,
    CapabilityConfig,
    EventBusConfig,
    ExtensionConfig,
    LoggingConfig,
    MemoryConfig,
    OrchestratorConfig,
    SchedulerConfig,
    SecurityConfig,
    get_settings,
    reset_settings,
)


class TestLoggingConfig:
    def test_defaults(self):
        cfg = LoggingConfig()
        assert cfg.level == "INFO"
        assert cfg.format == "json"
        assert cfg.output == "stdout"

    def test_custom(self):
        cfg = LoggingConfig(level="DEBUG", format="console", output="stderr")
        assert cfg.level == "DEBUG"
        assert cfg.format == "console"
        assert cfg.output == "stderr"


class TestEventBusConfig:
    def test_defaults(self):
        cfg = EventBusConfig()
        assert cfg.max_queue_size == 10000
        assert cfg.worker_count == 4
        assert cfg.enable_priority is True

    def test_custom(self):
        cfg = EventBusConfig(max_queue_size=5000, worker_count=2)
        assert cfg.max_queue_size == 5000
        assert cfg.worker_count == 2


class TestSchedulerConfig:
    def test_defaults(self):
        cfg = SchedulerConfig()
        assert cfg.max_workers == 8
        assert cfg.default_timeout_s == 30.0


class TestOrchestratorConfig:
    def test_defaults(self):
        cfg = OrchestratorConfig()
        assert cfg.max_concurrent_workflows == 100
        assert cfg.workflow_timeout_s == 300.0
        assert cfg.retry_max_attempts == 3


class TestCapabilityConfig:
    def test_defaults(self):
        cfg = CapabilityConfig()
        assert cfg.enable_ranking is True
        assert cfg.default_trust_score == 0.5
        assert "trust" in cfg.ranking_weights


class TestExtensionConfig:
    def test_defaults(self):
        cfg = ExtensionConfig()
        assert cfg.auto_load is False
        assert cfg.validate_on_load is True
        assert cfg.sandbox_enabled is False


class TestSecurityConfig:
    def test_defaults_zero_trust(self):
        cfg = SecurityConfig()
        assert cfg.default_deny is True
        assert cfg.permission_engine_enabled is True
        assert cfg.policy_engine_enabled is True


class TestMemoryConfig:
    def test_defaults(self):
        cfg = MemoryConfig()
        assert cfg.context_ttl_s == 3600
        assert cfg.session_ttl_s == 86400


class TestBrainConfig:
    def test_defaults_thinking_modes(self):
        cfg = BrainConfig()
        assert cfg.thinking_modes == ["fast", "balanced", "deep"]
        assert cfg.default_thinking_mode == "balanced"


class TestArgusSettings:
    def test_defaults(self):
        s = ArgusSettings()
        assert s.app_name == "argus"
        assert s.version == "0.1.0"
        assert s.environment == "development"
        assert isinstance(s.logging, LoggingConfig)
        assert isinstance(s.event_bus, EventBusConfig)
        assert isinstance(s.scheduler, SchedulerConfig)
        assert isinstance(s.orchestrator, OrchestratorConfig)
        assert isinstance(s.capability, CapabilityConfig)
        assert isinstance(s.extension, ExtensionConfig)
        assert isinstance(s.security, SecurityConfig)
        assert isinstance(s.memory, MemoryConfig)
        assert isinstance(s.brain, BrainConfig)

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("ARGUS_APP_NAME", "argus-test")
        monkeypatch.setenv("ARGUS_ENVIRONMENT", "production")
        monkeypatch.setenv("ARGUS_LOGGING__LEVEL", "DEBUG")
        monkeypatch.setenv("ARGUS_SECURITY__DEFAULT_DENY", "false")
        s = ArgusSettings()
        assert s.app_name == "argus-test"
        assert s.environment == "production"
        assert s.logging.level == "DEBUG"
        assert s.security.default_deny is False

    def test_data_dir_creation(self, tmp_path):
        data_dir = tmp_path / "argus_data"
        s = ArgusSettings(data_dir=data_dir)
        resolved = s.get_data_dir()
        assert resolved.exists()
        assert resolved == data_dir.resolve()


class TestSettingsSingleton:
    def test_get_settings_singleton(self):
        reset_settings()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_reset_settings(self):
        reset_settings()
        s1 = get_settings()
        reset_settings()
        s2 = get_settings()
        assert s1 is not s2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
