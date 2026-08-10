"""Test Contracts — Argus."""
from __future__ import annotations

import pytest

from argus.contracts.types import (
    Request,
    Decision,
    CapabilityRequest,
    ExecutionResultContract,
    FailureObject,
    ContractValidationError,
    validate_contract,
)


class TestRequest:
    def test_valid(self):
        r = Request(message="do something")
        r.validate()  # no raise

    def test_empty_message_raises(self):
        with pytest.raises(ContractValidationError):
            Request(message="").validate()

    def test_whitespace_message_raises(self):
        with pytest.raises(ContractValidationError):
            Request(message="   ").validate()


class TestDecision:
    def test_valid(self):
        d = Decision(choice="A", confidence=0.9)
        d.validate()

    def test_empty_choice_raises(self):
        with pytest.raises(ContractValidationError):
            Decision(choice="").validate()

    def test_confidence_out_of_range(self):
        with pytest.raises(ContractValidationError):
            Decision(choice="A", confidence=1.5).validate()


class TestCapabilityRequest:
    def test_valid(self):
        c = CapabilityRequest(capability_id="math.add", params={"a": 1, "b": 2})
        c.validate()

    def test_empty_id_raises(self):
        with pytest.raises(ContractValidationError):
            CapabilityRequest(capability_id="").validate()


class TestExecutionResultContract:
    def test_success_shape(self):
        r = ExecutionResultContract(success=True, output="5", duration_ms=10)
        assert r.success is True
        assert r.output == "5"

    def test_failure_with_object(self):
        f = FailureObject(code="E1", reason="boom", retryable=True)
        r = ExecutionResultContract(success=False, error=f)
        assert r.error.retryable is True
        assert r.error.to_dict()["code"] == "E1"


class TestValidateContract:
    def test_valid_contract(self):
        validate_contract(Request(message="x"))  # no raise

    def test_non_contract_raises(self):
        with pytest.raises(ContractValidationError):
            validate_contract({"not": "contract"})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])