"""Extension Manifest — Argus (Spec §36)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ExtensionType(str, Enum):
    CAPABILITY = "capability"
    CONNECTOR = "connector"
    TOOL = "tool"
    MODEL = "model"
    MEMORY = "memory"
    WORKFLOW = "workflow"
    TRIGGER = "trigger"
    SECURITY = "security"
    UI = "ui"


class ManifestValidationError(ValueError):
    """Raised when a manifest is invalid."""


@dataclass
class ExtensionManifest:
    """Extension manifest (Spec §36)."""

    extension_id: str
    name: str
    version: str
    author: str
    type: ExtensionType
    runtime: str = "argus"
    entry_point: str = ""
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    min_core_version: str = "1.0.0"
    description: str = ""

    def validate(self) -> None:
        if not self.extension_id or not self.extension_id.strip():
            raise ManifestValidationError("extension_id is required")
        if not self.name or not self.name.strip():
            raise ManifestValidationError("name is required")
        if not self.version:
            raise ManifestValidationError("version is required")
        if not self.author:
            raise ManifestValidationError("author is required")
        if not self.entry_point:
            raise ManifestValidationError("entry_point is required")
        if self.min_core_version and not _is_semver(self.min_core_version):
            raise ManifestValidationError(
                f"min_core_version must be semver, got {self.min_core_version!r}",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "extension_id": self.extension_id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "type": self.type.value,
            "runtime": self.runtime,
            "entry_point": self.entry_point,
            "capabilities": list(self.capabilities),
            "permissions": list(self.permissions),
            "dependencies": list(self.dependencies),
            "min_core_version": self.min_core_version,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtensionManifest:
        return cls(
            extension_id=data["extension_id"],
            name=data["name"],
            version=data["version"],
            author=data["author"],
            type=ExtensionType(data["type"]),
            runtime=data.get("runtime", "argus"),
            entry_point=data.get("entry_point", ""),
            capabilities=list(data.get("capabilities", [])),
            permissions=list(data.get("permissions", [])),
            dependencies=list(data.get("dependencies", [])),
            min_core_version=data.get("min_core_version", "1.0.0"),
            description=data.get("description", ""),
        )


def _is_semver(v: str) -> bool:
    parts = v.split(".")
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def load_manifest(path: Path | str) -> ExtensionManifest:
    """Load and validate a manifest from JSON file."""
    p = Path(path)
    if not p.exists():
        raise ManifestValidationError(f"Manifest file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ManifestValidationError(f"Invalid JSON in manifest {p}: {e}")
    manifest = ExtensionManifest.from_dict(data)
    manifest.validate()
    return manifest
