"""Test Gateway Auth — Argus."""
from __future__ import annotations

import pytest
import time

from argus.gateway.auth import AuthManager, TokenData, create_auth_manager


class TestAuthManager:
    """Test AuthManager functionality."""

    def test_create_token_basic(self):
        auth = AuthManager(secret_key="test-secret")
        token = auth.create_token("user123")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_token_with_scopes(self):
        auth = AuthManager(secret_key="test-secret")
        token = auth.create_token("user123", scopes=["read", "write"])
        assert isinstance(token, str)

    def test_verify_valid_token(self):
        auth = AuthManager(secret_key="test-secret")
        token = auth.create_token("user123", scopes=["read"])
        token_data = auth.verify_token(token)
        assert token_data is not None
        assert token_data.sub == "user123"
        assert "read" in token_data.scopes

    def test_verify_invalid_token(self):
        auth = AuthManager(secret_key="test-secret")
        token_data = auth.verify_token("invalid-token")
        assert token_data is None

    def test_verify_tampered_token(self):
        auth = AuthManager(secret_key="test-secret")
        token = auth.create_token("user123")
        # Tamper with token
        tampered = token[:-1] + ("x" if token[-1] != "x" else "y")
        token_data = auth.verify_token(tampered)
        assert token_data is None

    def test_token_expiration(self):
        auth = AuthManager(secret_key="test-secret", default_ttl_seconds=1)
        token = auth.create_token("user123")
        token_data = auth.verify_token(token)
        assert token_data is not None

        time.sleep(1.1)
        token_data = auth.verify_token(token)
        assert token_data is None

    def test_api_key_management(self):
        auth = AuthManager(secret_key="test-secret")
        td = TokenData(sub="api-user", scopes=["api"])
        auth.add_api_key("sk-test-123", td)

        validated = auth.validate_api_key("sk-test-123")
        assert validated is not None
        assert validated.sub == "api-user"

        assert auth.validate_api_key("invalid") is None

        revoked = auth.revoke_api_key("sk-test-123")
        assert revoked is True
        assert auth.validate_api_key("sk-test-123") is None

    def test_has_scope(self):
        auth = AuthManager(secret_key="test-secret")
        td = TokenData(sub="user", scopes=["read", "write"])
        assert auth.has_scope(td, "read") is True
        assert auth.has_scope(td, "write") is True
        assert auth.has_scope(td, "delete") is False

        td_wildcard = TokenData(sub="admin", scopes=["*"])
        assert auth.has_scope(td_wildcard, "anything") is True

    def test_different_secret_keys(self):
        auth1 = AuthManager(secret_key="secret1")
        auth2 = AuthManager(secret_key="secret2")

        token = auth1.create_token("user123")
        assert auth1.verify_token(token) is not None
        assert auth2.verify_token(token) is None


class TestCreateAuthManager:
    """Test factory function."""

    def test_factory_creates_manager(self):
        auth = create_auth_manager(secret_key="factory-secret")
        assert isinstance(auth, AuthManager)
        token = auth.create_token("test")
        assert auth.verify_token(token) is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])