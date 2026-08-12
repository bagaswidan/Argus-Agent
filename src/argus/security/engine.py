"""Security Engine — Argus.

Zero-trust permission enforcement (Spec §1, §30): every capability execution
is checked against a permission policy before it runs. Default deny.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class SecurityError(Exception):
    """Raised when a permission check fails."""


@dataclass
class Permission:
    """A permission grant: allow/deny a resource+action for a subject."""

    subject: str  # user, agent, extension id
    resource: str  # capability id, "secret", "memory", "workspace", "*"
    action: str  # "execute", "read", "write", "delete", "*"
    allow: bool = True
    reason: str = ""

    def matches(self, subject: str, resource: str, action: str) -> bool:
        from fnmatch import fnmatch

        return (
            (self.subject == subject or self.subject == "*" or fnmatch(subject, self.subject))
            and (self.resource == resource or self.resource == "*" or fnmatch(resource, self.resource))
            and (self.action == action or self.action == "*" or fnmatch(action, self.action))
        )


@dataclass
class AccessRequest:
    """A request to check access."""

    subject: str
    resource: str
    action: str = "execute"
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class AccessDecision:
    allowed: bool
    subject: str = ""
    resource: str = ""
    action: str = ""
    reason: str = ""


class SecurityEngine:
    """Zero-trust permission engine. Default deny; explicit allow to pass."""

    def __init__(self) -> None:
        self._permissions: list[Permission] = []
        self._audit: list[AccessDecision] = []
        self._max_audit = 1000
        self.default_deny = True

    def allow(self, subject: str, resource: str, action: str = "execute", reason: str = "") -> None:
        """Grant access. Order matters: first match wins."""
        self._permissions.append(Permission(subject, resource, action, allow=True, reason=reason))

    def deny(self, subject: str, resource: str, action: str = "*", reason: str = "") -> None:
        """Explicitly deny. Order matters: first match wins."""
        self._permissions.append(Permission(subject, resource, action, allow=False, reason=reason))

    def check(self, req: AccessRequest) -> AccessDecision:
        """Evaluate access. First matching permission wins; default deny."""
        decision = AccessDecision(
            allowed=False,
            subject=req.subject,
            resource=req.resource,
            action=req.action,
            reason="denied by default (zero-trust)",
        )
        for perm in self._permissions:
            if perm.matches(req.subject, req.resource, req.action):
                decision = AccessDecision(
                    allowed=perm.allow,
                    subject=req.subject,
                    resource=req.resource,
                    action=req.action,
                    reason=perm.reason or ("allowed" if perm.allow else "denied"),
                )
                break

        self._audit.append(decision)
        if len(self._audit) > self._max_audit:
            self._audit = self._audit[-self._max_audit:]
        return decision

    def enforce(self, req: AccessRequest) -> None:
        """Check and raise SecurityError if not allowed."""
        decision = self.check(req)
        if not decision.allowed:
            raise SecurityError(
                f"Access denied: {req.subject} → {req.action} on {req.resource} ({decision.reason})",
            )

    def can(self, subject: str, resource: str, action: str = "execute") -> bool:
        return self.check(AccessRequest(subject, resource, action)).allowed

    def audit_log(self, limit: int = 100) -> list[AccessDecision]:
        return list(self._audit[-limit:])


def create_security_engine() -> SecurityEngine:
    return SecurityEngine()
