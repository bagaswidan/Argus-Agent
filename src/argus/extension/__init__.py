"""Extension — Argus.

Extension architecture per Spec §35-39: Manifest, Lifecycle, RPC contract,
and Extension Manager. Extensions implement capabilities outside core.
"""
from __future__ import annotations

from argus.extension.manifest import (
    ExtensionManifest,
    ExtensionType,
    load_manifest,
    ManifestValidationError,
)
from argus.extension.rpc import (
    RpcResponse,
    ExtensionRpc,
    create_rpc_response,
    RpcError,
)
from argus.extension.manager import ExtensionManager, ExtensionState, create_extension_manager

__all__ = [
    "ExtensionManifest",
    "ExtensionType",
    "load_manifest",
    "ManifestValidationError",
    "RpcResponse",
    "ExtensionRpc",
    "create_rpc_response",
    "RpcError",
    "ExtensionManager",
    "ExtensionState",
    "create_extension_manager",
]