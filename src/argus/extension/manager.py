"""Extension Manager — Argus (Spec §37).

Lifecycle: Install -> Validate -> Load -> Initialize -> Ready -> Running
-> Update -> Unload -> Remove. Validation must complete before Ready.
Crash of one extension must not stop core (isolated by design).
"""
from __future__ import annotations

import contextlib
import importlib.util
import logging
from enum import StrEnum
from pathlib import Path
from typing import Any

from argus.extension.manifest import ExtensionManifest, ManifestValidationError
from argus.extension.rpc import ExtensionRpc, RpcResponse

logger = logging.getLogger(__name__)


class ExtensionState(StrEnum):
    INSTALLED = "installed"
    VALIDATED = "validated"
    LOADED = "loaded"
    INITIALIZED = "initialized"
    READY = "ready"
    RUNNING = "running"
    UPDATED = "updated"
    UNLOADED = "unloaded"
    REMOVED = "removed"
    FAILED = "failed"


class ExtensionManager:
    """Manages extension lifecycle.

    Extensions are isolated; a crash in one does not stop the core (each call is wrapped).
    """

    def __init__(self) -> None:
        self._extensions: dict[str, ExtensionManifest] = {}
        self._instances: dict[str, ExtensionRpc] = {}
        self._states: dict[str, ExtensionState] = {}
        self._load_dirs: list[Path] = []

    def add_load_dir(self, path: Path | str) -> None:
        self._load_dirs.append(Path(path))

    # --- lifecycle ---

    def install(self, manifest: ExtensionManifest) -> bool:
        """Validate and register manifest (Install -> Validate)."""
        manifest.validate()
        if manifest.extension_id in self._extensions:
            raise ManifestValidationError(
                f"Extension {manifest.extension_id} already installed",
            )
        self._extensions[manifest.extension_id] = manifest
        self._states[manifest.extension_id] = ExtensionState.VALIDATED
        return True

    def load(self, extension_id: str, module_path: Path | None = None) -> bool:
        """Load extension implementation (Load)."""
        manifest = self._get(extension_id)
        target = module_path or self._resolve_entry_point(manifest)
        if target is None or not Path(target).exists():
            self._states[extension_id] = ExtensionState.FAILED
            raise ManifestValidationError(
                f"Entry point not found for {extension_id}: {manifest.entry_point}",
            )
        spec = importlib.util.spec_from_file_location(
            f"argus_ext_{manifest.extension_id.replace('-', '_')}", target,
        )
        if spec is None or spec.loader is None:
            raise ManifestValidationError(f"Could not load module spec for {extension_id}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        instance = self._build_instance(module, manifest)
        self._instances[extension_id] = instance
        self._states[extension_id] = ExtensionState.LOADED
        return True

    def initialize(self, extension_id: str, config: dict[str, Any] | None = None) -> RpcResponse:
        """Initialize (Initialize -> Ready)."""
        instance = self._get_instance(extension_id)
        try:
            resp = instance.initialize(config)
            if resp.ok:
                self._states[extension_id] = ExtensionState.READY
            return resp
        except Exception as e:
            self._states[extension_id] = ExtensionState.FAILED
            return RpcResponse(status="error", error={"code": "INIT_FAILED", "message": str(e)})

    def execute(self, extension_id: str, params: dict[str, Any]) -> RpcResponse:
        """Execute (Running). Isolated: errors are contained."""
        instance = self._get_instance(extension_id)
        if self._states.get(extension_id) not in (ExtensionState.READY, ExtensionState.RUNNING):
            self._states[extension_id] = ExtensionState.RUNNING
        try:
            return instance.execute(params)
        except Exception as e:
            self._states[extension_id] = ExtensionState.FAILED
            return RpcResponse(
                status="error",
                error={"code": "EXEC_FAILED", "message": str(e)},
            )

    def health(self, extension_id: str) -> RpcResponse:
        instance = self._get_instance(extension_id)
        try:
            return instance.health()
        except Exception as e:
            return RpcResponse(status="error", error={"code": "HEALTH_FAILED", "message": str(e)})

    def configure(self, extension_id: str, config: dict[str, Any]) -> RpcResponse:
        instance = self._get_instance(extension_id)
        try:
            return instance.configure(config)
        except Exception as e:
            return RpcResponse(status="error", error={"code": "CONFIG_FAILED", "message": str(e)})

    def unload(self, extension_id: str) -> bool:
        """Unload without restarting core (Spec §40)."""
        instance = self._instances.get(extension_id)
        if instance is not None:
            with contextlib.suppress(Exception):
                instance.shutdown()
        self._instances.pop(extension_id, None)
        self._states[extension_id] = ExtensionState.UNLOADED
        return True

    def remove(self, extension_id: str) -> bool:
        self.unload(extension_id)
        self._extensions.pop(extension_id, None)
        self._states[extension_id] = ExtensionState.REMOVED
        return True

    def reload(self, extension_id: str) -> bool:
        """Unload then load from the same entry point (Update)."""
        manifest = self._extensions.get(extension_id)
        if manifest is None:
            return False
        self.unload(extension_id)
        self.load(extension_id)
        self._states[extension_id] = ExtensionState.UPDATED
        return True

    # --- queries ---

    def state(self, extension_id: str) -> ExtensionState | None:
        return self._states.get(extension_id)

    def list_extensions(self) -> list[ExtensionManifest]:
        return list(self._extensions.values())

    def get(self, extension_id: str) -> ExtensionManifest | None:
        return self._extensions.get(extension_id)

    # --- internals ---

    def _get(self, extension_id: str) -> ExtensionManifest:
        manifest = self._extensions.get(extension_id)
        if manifest is None:
            raise ManifestValidationError(f"Extension not installed: {extension_id}")
        return manifest

    def _get_instance(self, extension_id: str) -> ExtensionRpc:
        instance = self._instances.get(extension_id)
        if instance is None:
            raise ManifestValidationError(
                f"Extension not loaded: {extension_id} (call load() first)",
            )
        return instance

    def _resolve_entry_point(self, manifest: ExtensionManifest) -> Path | None:
        ep = Path(manifest.entry_point)
        if ep.is_absolute() and ep.exists():
            return ep
        for d in self._load_dirs:
            candidate = d / manifest.extension_id / ep
            if candidate.exists():
                return candidate
        return None

    def _build_instance(self, module: Any, manifest: ExtensionManifest) -> ExtensionRpc:
        """Find the ExtensionRpc subclass in the module."""
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, ExtensionRpc)
                and obj is not ExtensionRpc
            ):
                return obj()
        raise ManifestValidationError(
            f"No ExtensionRpc subclass found in {manifest.entry_point}",
        )


def create_extension_manager() -> ExtensionManager:
    return ExtensionManager()
