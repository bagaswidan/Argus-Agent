"""Test Argus CLI — entry point."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from argus.cli.main import app

runner = CliRunner()


class TestCliVersion:
    def test_version(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "Argus v" in result.output


class TestCliStatus:
    def test_status(self):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Argus v" in result.output
        assert "Auth" in result.output
        assert "SecretVault" in result.output


class TestCliSmoke:
    def test_smoke_passes(self):
        result = runner.invoke(app, ["smoke"])
        assert result.exit_code == 0
        assert "ALL 10 STAGES PASSED" in result.output


class TestSmokeModule:
    def test_run_smoke_returns_true(self):
        from argus._smoke import run_smoke
        assert run_smoke(verbose=False) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])