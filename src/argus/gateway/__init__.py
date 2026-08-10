"""Gateway + Connector — Argus.

HTTP/gRPC server, authentication, and platform adapter framework.
"""
from __future__ import annotations

from argus.gateway.server import GatewayServer, GatewayConfig
from argus.gateway.auth import AuthManager, TokenData
from argus.gateway.adapters import PlatformAdapter, AdapterRegistry

__all__ = [
    "GatewayServer",
    "GatewayConfig",
    "AuthManager",
    "TokenData",
    "PlatformAdapter",
    "AdapterRegistry",
]