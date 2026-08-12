"""Extension — Argus.

Extension architecture per Spec §35-39: Manifest, Lifecycle, RPC contract,
and Extension Manager. Extensions implement capabilities outside core.
"""
from __future__ import annotations

from argus.extension.manager import ExtensionManager, ExtensionState, create_extension_manager
from argus.extension.manifest import (
    ExtensionManifest,
    ExtensionType,
    ManifestValidationError,
    load_manifest,
)
from argus.extension.rpc import (
    ExtensionRpc,
    RpcError,
    RpcResponse,
    create_rpc_response,
)

__all__ = [
    "ExtensionManager",
    "ExtensionManifest",
    "ExtensionRpc",
    "ExtensionState",
    "ExtensionType",
    "ManifestValidationError",
    "RpcError",
    "RpcResponse",
    "create_extension_manager",
    "create_rpc_response",
    "load_manifest",
]
