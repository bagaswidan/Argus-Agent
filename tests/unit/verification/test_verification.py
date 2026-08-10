"""Test Verification Stage — Argus (Refinement 5)."""
from __future__ import annotations

import pytest

from argus.verification import (
    VerificationStage,
    check_not_empty,
    check_no_error_flag,
    check_no_secret_leak,
    check_success_flag,
    create_verification_stage,
)


class TestBuiltinChecks:
    def test_not_empty_ok(self):
        assert check_not_empty({"output": "hello"}) == (True, "output present")

    def test_not_empty_fails(self):
        ok, _ = check_not_empty({"output": "   "})
        assert ok is False

    def test_no_error_flag_ok(self):
        assert check_no_error_flag({"error": None})[0] is True

    def test_no_error_flag_fails(self):
        ok, msg = check_no_error_flag({"error": "boom"})
        assert ok is False
        assert "boom" in msg

    def test_no_secret_ok(self):
        assert check_no_secret_leak({"output": "deployed to staging"})[0] is True

    def test_no_secret_detects_sk_key(self):
        ok, _ = check_no_secret_leak({"output": "key: sk-abc1234567890xyz"})
        assert ok is False

    def test_no_secret_detects_api_key(self):
        ok, _ = check_no_secret_leak({"output": "api_key=supersecretvalue123456"})
        assert ok is False

    def test_success_flag(self):
        assert check_success_flag({"success": True})[0] is True
        assert check_success_flag({"success": False})[0] is False


class TestVerificationStage:
    def test_passes_clean_result(self):
        stage = create_verification_stage()
        result = stage.verify({"output": "all good", "success": True, "error": None})
        assert result.passed is True
        assert result.checks_run == 4
        assert result.failures == []

    def test_fails_on_empty(self):
        stage = create_verification_stage()
        result = stage.verify({"output": "", "success": True})
        assert result.passed is False
        assert result.failures[0]["check"] == "not_empty"

    def test_short_circuits_on_first_failure(self):
        stage = create_verification_stage()
        result = stage.verify({"output": "", "success": False, "error": "x"})
        # stops after not_empty fails
        assert result.checks_run == 1
        assert result.failures[0]["check"] == "not_empty"

    def test_custom_check(self):
        stage = create_verification_stage()

        def must_start_with_ok(result):
            return (str(result.get("output", "")).startswith("OK"), "prefix")

        stage.add_check("prefix", must_start_with_ok)
        assert stage.verify({"output": "OK fine"}).passed is True
        assert stage.verify({"output": "bad"}).passed is False

    def test_check_exception_becomes_failure(self):
        stage = create_verification_stage()

        def broken(result):
            raise RuntimeError("check crash")

        stage.add_check("broken", broken)
        result = stage.verify({"output": "x"})
        assert result.passed is False
        assert "check crash" in result.failures[0]["message"]

    def test_to_dict_shape(self):
        stage = create_verification_stage()
        d = stage.verify({"output": "x"}).to_dict()
        assert set(d) == {"passed", "checks_run", "failures", "notes"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
