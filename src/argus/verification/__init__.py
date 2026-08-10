"""Verification Stage — Argus (Refinement 5).

A distinct pipeline step that validates an execution result before it's
allowed to become a response. Enforces the "Verify Before Respond"
constitution principle with pluggable checks.

Checks run in order; the first failure short-circuits with a report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

CheckFn = Callable[[dict[str, Any]], tuple[bool, str]]


@dataclass
class VerificationResult:
    """Outcome of running the verification stage."""

    passed: bool
    checks_run: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks_run": self.checks_run,
            "failures": self.failures,
            "notes": self.notes,
        }


# --- built-in checks ------------------------------------------------------
def check_not_empty(result: dict[str, Any]) -> tuple[bool, str]:
    output = result.get("output")
    if output is None or (isinstance(output, str) and not output.strip()):
        return False, "output is empty"
    return True, "output present"


def check_no_error_flag(result: dict[str, Any]) -> tuple[bool, str]:
    if result.get("error"):
        return False, f"error flag set: {result['error']}"
    return True, "no error flag"


def check_no_secret_leak(result: dict[str, Any]) -> tuple[bool, str]:
    output = str(result.get("output", ""))
    # looks like sk-... / api_key=... / password=...
    patterns = [
        r"(sk-[A-Za-z0-9]{12,})",
        r"(api[_-]?key[\s:=]+['\"]?[\w\-.]{16,})",
        r"(password[\s:=]+['\"]?[\w\-!@#$%^&*]{8,})",
    ]
    for pat in patterns:
        m = re.search(pat, output, re.IGNORECASE)
        if m:
            return False, f"possible secret in output: {m.group(1)[:16]}..."
    return True, "no secret-like patterns"


def check_success_flag(result: dict[str, Any]) -> tuple[bool, str]:
    if result.get("success") is False:
        return False, "success flag is false"
    return True, "success flag ok"


DEFAULT_CHECKS: list[tuple[str, CheckFn]] = [
    ("not_empty", check_not_empty),
    ("no_error", check_no_error_flag),
    ("no_secret", check_no_secret_leak),
    ("success", check_success_flag),
]


class VerificationStage:
    """Runs pluggable checks over an execution result."""

    def __init__(self, checks: Optional[list[tuple[str, CheckFn]]] = None):
        self.checks = checks or list(DEFAULT_CHECKS)

    def add_check(self, name: str, fn: CheckFn) -> None:
        self.checks.append((name, fn))

    def verify(self, result: dict[str, Any]) -> VerificationResult:
        v = VerificationResult(passed=True)
        for name, fn in self.checks:
            v.checks_run += 1
            try:
                ok, message = fn(result)
            except Exception as exc:  # noqa: BLE001
                ok, message = False, f"check raised: {exc}"
            if not ok:
                v.passed = False
                v.failures.append({"check": name, "message": message})
                break  # short-circuit on first failure
        return v


def create_verification_stage() -> VerificationStage:
    return VerificationStage()
