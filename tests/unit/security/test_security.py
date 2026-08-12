"""Test Security Engine — Argus."""
from __future__ import annotations

import pytest

from argus.security.engine import (
    AccessRequest,
    SecurityError,
    create_security_engine,
)


class TestSecurityEngine:
    def test_default_deny(self):
        engine = create_security_engine()
        assert engine.can("user1", "anything") is False

    def test_explicit_allow(self):
        engine = create_security_engine()
        engine.allow("user1", "math.add", "execute")
        assert engine.can("user1", "math.add") is True

    def test_other_user_denied(self):
        engine = create_security_engine()
        engine.allow("user1", "math.add")
        assert engine.can("user2", "math.add") is False

    def test_wildcard_allow(self):
        engine = create_security_engine()
        engine.allow("*", "math.*", "execute")
        assert engine.can("anyone", "math.add") is True
        assert engine.can("anyone", "math.subtract") is True
        assert engine.can("anyone", "file.read") is False

    def test_explicit_deny_overrides_default(self):
        engine = create_security_engine()
        engine.deny("user1", "secret", "read", reason="no secrets for you")
        assert engine.can("user1", "secret", "read") is False

    def test_first_match_wins(self):
        engine = create_security_engine()
        engine.allow("user1", "*", "*")
        engine.deny("user1", "secret", "*")
        # allow first, so allowed
        assert engine.can("user1", "secret", "read") is True

    def test_deny_first_wins(self):
        engine = create_security_engine()
        engine.deny("user1", "secret", "*")
        engine.allow("user1", "*", "*")
        assert engine.can("user1", "secret", "read") is False
        assert engine.can("user1", "memory", "write") is True

    def test_enforce_raises(self):
        engine = create_security_engine()
        with pytest.raises(SecurityError):
            engine.enforce(AccessRequest("user1", "secret", "read"))

    def test_enforce_passes_when_allowed(self):
        engine = create_security_engine()
        engine.allow("user1", "math.add")
        engine.enforce(AccessRequest("user1", "math.add"))  # no raise

    def test_audit_log(self):
        engine = create_security_engine()
        engine.can("u", "r")
        engine.can("u", "r2")
        log = engine.audit_log()
        assert len(log) == 2
        assert log[0].allowed is False
        assert log[0].subject == "u"

    def test_action_specific(self):
        engine = create_security_engine()
        engine.allow("user1", "workspace", "read")
        assert engine.can("user1", "workspace", "read") is True
        assert engine.can("user1", "workspace", "write") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
