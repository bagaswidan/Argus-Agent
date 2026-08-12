"""Authentication — Argus Gateway.

Token-based auth with JWT support, API keys, and session management.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    # PyJWT is an optional dependency; when it is not installed we fall back
    # to the built-in HMAC token scheme. Stub the module as Any for mypy.
    jwt: Any
    JWT_AVAILABLE = True
else:
    try:
        import jwt

        JWT_AVAILABLE = True
    except ImportError:
        JWT_AVAILABLE = False


@dataclass
class TokenData:
    """Decoded token data."""

    sub: str  # subject (user/agent id)
    scopes: list[str] = field(default_factory=list)
    exp: int | None = None  # expiration timestamp
    iat: int | None = None  # issued at
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.exp is None:
            return False
        return time.time() > self.exp

    def to_dict(self) -> dict[str, Any]:
        return {
            "sub": self.sub,
            "scopes": self.scopes,
            "exp": self.exp,
            "iat": self.iat,
            **self.extra,
        }


class AuthManager:
    """Manages authentication for the gateway."""

    def __init__(
        self,
        secret_key: str | None = None,
        algorithm: str = "HS256",
        default_ttl_seconds: int = 3600,
        api_keys: dict[str, TokenData] | None = None,
    ):
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.algorithm = algorithm
        self.default_ttl = default_ttl_seconds
        self.api_keys = api_keys or {}

    def create_token(
        self,
        sub: str,
        scopes: list[str] | None = None,
        ttl_seconds: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Create a new JWT token."""
        if not JWT_AVAILABLE:
            # Fallback: simple token format: sub:scopes:timestamp:signature
            iat = int(time.time())
            exp = iat + (ttl_seconds or self.default_ttl)
            scopes_str = ",".join(scopes) if scopes else ""
            payload = f"{sub}:{scopes_str}:{iat}:{exp}"
            sig = hmac.new(
                self.secret_key.encode(), payload.encode(), hashlib.sha256,
            ).hexdigest()[:16]
            return f"{payload}:{sig}"

        now = int(time.time())
        exp = now + (ttl_seconds or self.default_ttl)

        # Place standard claims *after* `extra` so they cannot be overridden
        # by unexpected keys supplied by the caller.
        claims: dict[str, Any] = {
            **(extra or {}),
            "sub": sub,
            "scopes": scopes if scopes is not None else [],
            "iat": now,
            "exp": exp,
        }
        return cast("str", jwt.encode(claims, self.secret_key, algorithm=self.algorithm))

    def verify_token(self, token: str) -> TokenData | None:
        """Verify and decode a token."""
        if not JWT_AVAILABLE:
            return self._verify_simple_token(token)

        try:
            payload = jwt.decode(
                token, self.secret_key, algorithms=[self.algorithm],
            )
            return TokenData(
                sub=payload["sub"],
                scopes=payload.get("scopes", []),
                exp=payload.get("exp"),
                iat=payload.get("iat"),
                extra={k: v for k, v in payload.items() if k not in ("sub", "scopes", "exp", "iat")},
            )
        except jwt.InvalidTokenError:
            return None

    def _verify_simple_token(self, token: str) -> TokenData | None:
        """Verify simple token format (fallback when jwt not available)."""
        parts = token.split(":")
        if len(parts) != 5:
            return None
        sub, scopes_str, iat_str, exp_str, sig = parts
        try:
            iat = int(iat_str)
            exp = int(exp_str)
        except ValueError:
            return None

        scopes = scopes_str.split(",") if scopes_str else []

        payload = f"{sub}:{scopes_str}:{iat}:{exp}"
        expected_sig = hmac.new(
            self.secret_key.encode(), payload.encode(), hashlib.sha256,
        ).hexdigest()[:16]

        if not hmac.compare_digest(sig, expected_sig):
            return None

        if time.time() > exp:
            return None

        return TokenData(sub=sub, scopes=scopes, iat=iat, exp=exp)

    def validate_api_key(self, api_key: str) -> TokenData | None:
        """Validate an API key."""
        return self.api_keys.get(api_key)

    def add_api_key(self, api_key: str, token_data: TokenData) -> None:
        """Register an API key."""
        self.api_keys[api_key] = token_data

    def revoke_api_key(self, api_key: str) -> bool:
        """Revoke an API key."""
        if api_key in self.api_keys:
            del self.api_keys[api_key]
            return True
        return False

    def has_scope(self, token_data: TokenData, required_scope: str) -> bool:
        """Check if token has required scope."""
        return required_scope in token_data.scopes or "*" in token_data.scopes


def create_auth_manager(
    secret_key: str | None = None,
    api_keys: dict[str, TokenData] | None = None,
) -> AuthManager:
    """Factory function to create an auth manager."""
    return AuthManager(secret_key=secret_key, api_keys=api_keys)
