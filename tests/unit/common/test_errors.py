"""Test Error Model — Argus Core Foundation."""
from __future__ import annotations

import pytest

from argus.common.errors import (
    ArgusError,
    ConfigurationError,
    ValidationError,
    NotFoundError,
    InternalError,
    TimeoutError,
    ErrorCode,
)


class TestErrorCode:
    def test_error_code_values(self):
        assert ErrorCode.CONFIGURATION_ERROR == "CONFIGURATION_ERROR"
        assert ErrorCode.VALIDATION_ERROR == "VALIDATION_ERROR"
        assert ErrorCode.NOT_FOUND == "NOT_FOUND"
        assert ErrorCode.INTERNAL_ERROR == "INTERNAL_ERROR"


class TestArgusError:
    def test_base_error(self):
        err = ArgusError("base error", code="BASE_ERROR")
        assert str(err) == "[BASE_ERROR] base error"
        assert err.code == "BASE_ERROR"
        assert err.details == {}
        assert err.retryable is False
        # default correlation_id dibuat otomatis (UUID) untuk observability

    def test_error_with_details(self):
        # retryable adalah class attribute — tidak bisa override via init
        err = TimeoutError("timed out", code="TO", details={"key": "value"})
        assert err.details == {"key": "value"}
        assert err.retryable is True

    def test_error_chaining(self):
        try:
            raise ValueError("original")
        except ValueError as e:
            err = ArgusError("wrapped", code="WRAP").with_cause(e)
            assert err.__cause__ is e

    def test_to_dict(self):
        err = ArgusError("test", code="TEST", details={"foo": "bar"}, correlation_id="abc-123")
        d = err.to_dict()
        assert d["message"] == "test"
        assert d["code"] == "TEST"
        assert d["details"] == {"foo": "bar"}
        assert d["correlation_id"] == "abc-123"
        assert d["retryable"] is False


class TestSpecificErrors:
    def test_configuration_error(self):
        err = ConfigurationError("bad config", details={"path": "/etc/config.yaml"})
        assert err.code == ErrorCode.CONFIGURATION_ERROR
        assert "bad config" in str(err)

    def test_validation_error(self):
        err = ValidationError("invalid input", details={"field": "email"})
        assert err.code == ErrorCode.VALIDATION_ERROR
        assert err.retryable is False

    def test_not_found_error(self):
        err = NotFoundError("resource missing", details={"id": "123"})
        assert err.code == ErrorCode.NOT_FOUND

    def test_internal_error(self):
        err = InternalError("internal failure")
        assert err.code == ErrorCode.INTERNAL_ERROR


if __name__ == "__main__":
    pytest.main([__file__, "-v"])