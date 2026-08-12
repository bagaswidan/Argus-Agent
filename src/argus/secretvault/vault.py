"""SecretVault — Argus Phase 2.

Secure secret storage with encryption for API keys, tokens, credentials.
Uses Fernet (AES-128) for encryption at rest.
"""
from __future__ import annotations

import base64
import json
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

if TYPE_CHECKING:
    from types import TracebackType


@dataclass
class VaultConfig:
    """Configuration for SecretVault."""

    vault_path: Path
    master_key: bytes | None = None  # If None, derived from password
    password: str | None = None  # Used to derive master_key if not provided
    salt: bytes | None = None  # If None, generated on first init
    iterations: int = 100_000  # PBKDF2 iterations
    auto_save: bool = True  # Auto-save on every change


@dataclass
class SecretEntry:
    """A single secret entry."""

    key: str
    value: str
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "metadata": self.metadata,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecretEntry:
        return cls(
            key=data["key"],
            value=data["value"],
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
        )


class SecretVault:
    """Encrypted secret storage."""

    def __init__(self, config: VaultConfig):
        self.config = config
        self._lock = threading.RLock()
        self._fernet: Fernet | None = None
        self._secrets: dict[str, SecretEntry] = {}
        self._dirty = False
        self._init_vault()

    def _init_vault(self) -> None:
        """Initialize or load the vault."""
        # If vault exists, load salt from file first
        if self.config.vault_path.exists():
            self._load_salt_from_vault()
        # Generate new salt for new vault
        elif self.config.salt is None:
            self.config.salt = secrets.token_bytes(16)

        # Derive master key
        if self.config.master_key is None:
            if self.config.password is None:
                raise ValueError("Either master_key or password must be provided")
            self.config.master_key = self._derive_key(self.config.password)

        # Create Fernet instance
        self._fernet = Fernet(base64.urlsafe_b64encode(self.config.master_key[:32]))

        # Load existing vault if exists
        if self.config.vault_path.exists():
            self._load_vault()
        else:
            self._save_vault()

    def _load_salt_from_vault(self) -> None:
        """Load salt and iterations from existing vault file (stored in plaintext header)."""
        try:
            with open(self.config.vault_path, "rb") as f:
                # Read first 32 bytes as salt (salt is 16 bytes, but we store length-prefixed)
                # Format: salt_len (1 byte) + salt + iterations (4 bytes, big-endian) + encrypted_data
                salt_len = int.from_bytes(f.read(1), "big")
                if salt_len > 0:
                    self.config.salt = f.read(salt_len)
                else:
                    raise ValueError("Invalid vault format: missing salt")

                self.config.iterations = int.from_bytes(f.read(4), "big")
        except Exception:
            # If we can't read salt, generate new (will fail to decrypt existing vault)
            if self.config.salt is None:
                self.config.salt = secrets.token_bytes(16)
            self.config.iterations = 100_000

    def _derive_key(self, password: str) -> bytes:
        """Derive encryption key from password using PBKDF2."""
        salt = self.config.salt
        if salt is None:
            raise ValueError("Vault salt is not initialized")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.config.iterations,
        )
        return kdf.derive(password.encode())

    def _load_vault(self) -> None:
        """Load and decrypt vault from disk."""
        with open(self.config.vault_path, "rb") as f:
            # Read header: salt_len (1 byte) + salt + iterations (4 bytes) + encrypted_data
            salt_len = int.from_bytes(f.read(1), "big")
            if salt_len > 0:
                self.config.salt = f.read(salt_len)
            self.config.iterations = int.from_bytes(f.read(4), "big")
            encrypted_data = f.read()

        if not encrypted_data:
            return

        try:
            if self._fernet is None:
                raise RuntimeError("Vault is not initialized")
            decrypted = self._fernet.decrypt(encrypted_data)
            data = json.loads(decrypted.decode())
            self._secrets = {
                k: SecretEntry.from_dict(v) for k, v in data.get("secrets", {}).items()
            }
        except Exception as e:
            raise ValueError(f"Failed to load vault (wrong password?): {e}")

    def _save_vault(self) -> None:
        """Encrypt and save vault to disk."""
        salt = self.config.salt
        if salt is None:
            raise ValueError("Vault salt is not initialized")
        if self._fernet is None:
            raise RuntimeError("Vault is not initialized")

        data = {
            "version": 1,
            "salt": base64.b64encode(salt).decode(),
            "iterations": self.config.iterations,
            "secrets": {k: v.to_dict() for k, v in self._secrets.items()},
            "saved_at": datetime.now(UTC).isoformat(),
        }

        json_data = json.dumps(data).encode()
        encrypted = self._fernet.encrypt(json_data)

        # Write with plaintext header: salt_len (1 byte) + salt + iterations (4 bytes) + encrypted_data
        tmp_path = self.config.vault_path.with_suffix(".tmp")
        with open(tmp_path, "wb") as f:
            # Write salt length (1 byte) + salt
            f.write(len(salt).to_bytes(1, "big"))
            f.write(salt)
            # Write iterations (4 bytes, big-endian)
            f.write(self.config.iterations.to_bytes(4, "big"))
            # Write encrypted data
            f.write(encrypted)
        tmp_path.replace(self.config.vault_path)

    def set(
        self,
        key: str,
        value: str,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> SecretEntry:
        """Store a secret."""
        with self._lock:
            now = datetime.now(UTC)
            old = self._secrets.get(key)
            created_at = old.created_at if old else now
            entry = SecretEntry(
                key=key,
                value=value,
                metadata=metadata or {},
                tags=tags or [],
                created_at=created_at,
                updated_at=now,
                expires_at=expires_at,
            )
            self._secrets[key] = entry
            self._dirty = True
            if self.config.auto_save:
                self._save_vault()
            return entry

    def get(self, key: str) -> SecretEntry | None:
        """Retrieve a secret."""
        with self._lock:
            entry = self._secrets.get(key)
            if entry and entry.is_expired():
                self.delete(key)
                return None
            return entry

    def get_value(self, key: str) -> str | None:
        """Get just the secret value."""
        entry = self.get(key)
        return entry.value if entry else None

    def delete(self, key: str) -> bool:
        """Delete a secret."""
        with self._lock:
            if key in self._secrets:
                del self._secrets[key]
                self._dirty = True
                if self.config.auto_save:
                    self._save_vault()
                return True
            return False

    def list_keys(self, tag_filter: list[str] | None = None) -> list[str]:
        """List all secret keys, optionally filtered by tags."""
        with self._lock:
            keys = []
            for key, entry in self._secrets.items():
                if entry.is_expired():
                    continue
                if tag_filter:
                    if all(tag in entry.tags for tag in tag_filter):
                        keys.append(key)
                else:
                    keys.append(key)
            return sorted(keys)

    def list_entries(self, tag_filter: list[str] | None = None) -> list[SecretEntry]:
        """List all secret entries, optionally filtered by tags."""
        with self._lock:
            entries = []
            for entry in self._secrets.values():
                if entry.is_expired():
                    continue
                if tag_filter:
                    if all(tag in entry.tags for tag in tag_filter):
                        entries.append(entry)
                else:
                    entries.append(entry)
            return sorted(entries, key=lambda e: e.key)

    def update_metadata(self, key: str, metadata: dict[str, Any]) -> bool:
        """Update secret metadata."""
        with self._lock:
            entry = self._secrets.get(key)
            if not entry:
                return False
            entry.metadata.update(metadata)
            entry.updated_at = datetime.now(UTC)
            self._dirty = True
            if self.config.auto_save:
                self._save_vault()
            return True

    def add_tags(self, key: str, tags: list[str]) -> bool:
        """Add tags to a secret."""
        with self._lock:
            entry = self._secrets.get(key)
            if not entry:
                return False
            for tag in tags:
                if tag not in entry.tags:
                    entry.tags.append(tag)
            entry.updated_at = datetime.now(UTC)
            self._dirty = True
            if self.config.auto_save:
                self._save_vault()
            return True

    def remove_tags(self, key: str, tags: list[str]) -> bool:
        """Remove tags from a secret."""
        with self._lock:
            entry = self._secrets.get(key)
            if not entry:
                return False
            for tag in tags:
                if tag in entry.tags:
                    entry.tags.remove(tag)
            entry.updated_at = datetime.now(UTC)
            self._dirty = True
            if self.config.auto_save:
                self._save_vault()
            return True

    def cleanup_expired(self) -> int:
        """Remove all expired secrets. Returns count removed."""
        with self._lock:
            expired = [k for k, v in self._secrets.items() if v.is_expired()]
            for key in expired:
                del self._secrets[key]
            if expired:
                self._dirty = True
                if self.config.auto_save:
                    self._save_vault()
            return len(expired)

    def rotate_master_key(self, new_password: str) -> None:
        """Rotate the master encryption key."""
        with self._lock:
            # Decrypt all secrets with current key
            {k: v.value for k, v in self._secrets.items()}

            # Derive new key
            new_salt = secrets.token_bytes(16)
            new_key = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=new_salt,
                iterations=self.config.iterations,
            ).derive(new_password.encode())

            # Update config
            self.config.salt = new_salt
            self.config.master_key = new_key
            self.config.password = new_password
            self._fernet = Fernet(base64.urlsafe_b64encode(new_key[:32]))

            # Re-encrypt and save
            self._save_vault()

    def export_plaintext(self, password: str) -> dict[str, str]:
        """Export all secrets as plaintext (for backup)."""
        with self._lock:
            # Verify password
            test_key = self._derive_key(password)
            if test_key != self.config.master_key:
                raise ValueError("Incorrect password")

            return {k: v.value for k, v in self._secrets.items() if not v.is_expired()}

    def import_plaintext(self, secrets: dict[str, str], metadata: dict[str, dict] | None = None) -> int:
        """Import secrets from plaintext dict."""
        meta = metadata or {}
        count = 0
        for key, value in secrets.items():
            m = meta.get(key, {})
            self.set(key, value, metadata=m.get("metadata"), tags=m.get("tags"))
            count += 1
        return count

    def close(self) -> None:
        """Close vault, saving if dirty."""
        with self._lock:
            if self._dirty and self.config.auto_save:
                self._save_vault()

    def __enter__(self) -> SecretVault:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


def create_vault(
    vault_path: Path | str,
    password: str,
    salt: bytes | None = None,
) -> SecretVault:
    """Factory function to create a SecretVault."""
    config = VaultConfig(
        vault_path=Path(vault_path),
        password=password,
        salt=salt,
    )
    return SecretVault(config)
