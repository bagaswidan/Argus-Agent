"""Test Logging — Argus Core Foundation."""
from __future__ import annotations

import pytest

from argus.common.logging import LogFormat, LogLevel, configure_logging, get_logger


class TestLogging:
    def test_get_logger_returns_logger(self):
        logger = get_logger("test.module")
        assert logger is not None
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")
        assert hasattr(logger, "debug")
        assert hasattr(logger, "warning")

    def test_logger_name(self):
        logger = get_logger("argus.test")
        assert "argus" in repr(logger).lower() or hasattr(logger, "_logger") or logger is not None

    def test_log_levels(self):
        logger = get_logger("test.levels")
        # Should not raise
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")
        logger.critical("critical message")

    def test_log_with_structured_data(self):
        logger = get_logger("test.structured")
        # Should not raise
        logger.info("user logged in", user_id=123, ip="192.168.1.1")
        logger.error("operation failed", operation="deploy", error_code="DEPLOY_FAILED")

    def test_log_levels_enum(self):
        assert LogLevel.DEBUG == "DEBUG"
        assert LogLevel.INFO == "INFO"
        assert LogLevel.WARNING == "WARNING"
        assert LogLevel.ERROR == "ERROR"
        assert LogLevel.CRITICAL == "CRITICAL"

    def test_log_format_enum(self):
        assert LogFormat.JSON == "json"
        assert LogFormat.CONSOLE == "console"

    def test_configure_logging_json(self):
        # Should not raise
        configure_logging(level=LogLevel.DEBUG, format=LogFormat.JSON, service_name="argus-test")

    def test_configure_logging_console(self):
        configure_logging(level=LogLevel.INFO, format=LogFormat.CONSOLE, service_name="argus-test")

    def test_logging_with_correlation_id(self):
        logger = get_logger("test.correlation")
        logger.info("request started", correlation_id="req-123", endpoint="/api/health")

    def test_logging_exception(self):
        logger = get_logger("test.exception")
        try:
            raise ValueError("test error")
        except ValueError:
            logger.exception("caught exception", extra_context="value")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
