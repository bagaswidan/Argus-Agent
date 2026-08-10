"""Test SecretVault — Argus Phase 2."""
from __future__ import annotations

import pytest
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from argus.secretvault.vault import SecretVault, VaultConfig, SecretEntry, create_vault


class TestSecretEntry:
    """Test SecretEntry dataclass."""

    def test_creation(self):
        entry = SecretEntry(key="test", value="secret123")
        assert entry.key == "test"
        assert entry.value == "secret123"

    def test_is_expired_false(self):
        entry = SecretEntry(key="test", value="secret")
        assert entry.is_expired() is False

    def test_is_expired_true(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        entry = SecretEntry(key="test", value="secret", expires_at=past)
        assert entry.is_expired() is True

    def test_to_dict(self):
        entry = SecretEntry(key="test", value="secret", tags=["tag1"])
        d = entry.to_dict()
        assert d["key"] == "test"
        assert d["value"] == "secret"
        assert d["tags"] == ["tag1"]

    def test_from_dict(self):
        data = {
            "key": "test",
            "value": "secret",
            "metadata": {"env": "prod"},
            "tags": ["tag1"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": None,
        }
        entry = SecretEntry.from_dict(data)
        assert entry.key == "test"
        assert entry.value == "secret"
        assert entry.metadata == {"env": "prod"}
        assert entry.tags == ["tag1"]


class TestSecretVault:
    """Test SecretVault."""

    def test_create_vault(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / "test.vault"
            vault = create_vault(vault_path, "test-password")
            assert vault.config.vault_path == vault_path

    def test_set_and_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = create_vault(Path(tmpdir) / "test.vault", "test-password")
            vault.set("api_key", "sk-1234567890abcdef")
            entry = vault.get("api_key")
            assert entry is not None
            assert entry.value == "sk-1234567890abcdef"

    def test_get_value(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = create_vault(Path(tmpdir) / "test.vault", "test-password")
            vault.set("api_key", "sk-1234567890abcdef")
            value = vault.get_value("api_key")
            assert value == "sk-1234567890abcdef"

    def test_get_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = create_vault(Path(tmpdir) / "test.vault", "test-password")
            assert vault.get("nonexistent") is None
            assert vault.get_value("nonexistent") is None

    def test_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = create_vault(Path(tmpdir) / "test.vault", "test-password")
            vault.set("key1", "value1")
            assert vault.delete("key1") is True
            assert vault.get("key1") is None
            assert vault.delete("key1") is False

    def test_list_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = create_vault(Path(tmpdir) / "test.vault", "test-password")
            vault.set("key1", "value1", tags=["api"])
            vault.set("key2", "value2", tags=["db"])
            vault.set("key3", "value3", tags=["api", "prod"])

            all_keys = vault.list_keys()
            assert set(all_keys) == {"key1", "key2", "key3"}

            api_keys = vault.list_keys(tag_filter=["api"])
            assert set(api_keys) == {"key1", "key3"}

            prod_keys = vault.list_keys(tag_filter=["prod"])
            assert set(prod_keys) == {"key3"}

    def test_metadata_and_tags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = create_vault(Path(tmpdir) / "test.vault", "test-password")
            vault.set("key1", "value1", metadata={"env": "prod"}, tags=["api"])

            assert vault.update_metadata("key1", {"region": "us-east-1"}) is True
            entry = vault.get("key1")
            assert entry.metadata == {"env": "prod", "region": "us-east-1"}

            assert vault.add_tags("key1", ["v1", "stable"]) is True
            entry = vault.get("key1")
            assert set(entry.tags) == {"api", "v1", "stable"}

            assert vault.remove_tags("key1", ["api"]) is True
            entry = vault.get("key1")
            assert entry.tags == ["v1", "stable"]

    def test_expiration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = create_vault(Path(tmpdir) / "test.vault", "test-password")
            future = datetime.now(timezone.utc) + timedelta(hours=1)
            vault.set("key1", "value1", expires_at=future)
            assert vault.get("key1") is not None

            past = datetime.now(timezone.utc) - timedelta(hours=1)
            vault.set("key2", "value2", expires_at=past)
            assert vault.get("key2") is None

    def test_cleanup_expired(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = create_vault(Path(tmpdir) / "test.vault", "test-password")
            past = datetime.now(timezone.utc) - timedelta(hours=1)
            future = datetime.now(timezone.utc) + timedelta(hours=1)

            vault.set("expired1", "v1", expires_at=past)
            vault.set("expired2", "v2", expires_at=past)
            vault.set("active", "v3", expires_at=future)

            cleaned = vault.cleanup_expired()
            assert cleaned == 2
            assert vault.get("active") is not None
            assert vault.get("expired1") is None

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / "test.vault"

            # Create and populate
            vault1 = create_vault(vault_path, "password123")
            vault1.set("key1", "secret1")
            vault1.set("key2", "secret2", tags=["api"])
            vault1.close()

            # Reopen and verify
            vault2 = create_vault(vault_path, "password123")
            assert vault2.get_value("key1") == "secret1"
            assert vault2.get_value("key2") == "secret2"
            entry = vault2.get("key2")
            assert entry.tags == ["api"]

    def test_wrong_password_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / "test.vault"
            vault1 = create_vault(vault_path, "correct-password")
            vault1.set("key1", "secret1")
            vault1.close()

            # Try to open with wrong password
            with pytest.raises(ValueError):
                create_vault(vault_path, "wrong-password")

    def test_context_manager(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / "test.vault"
            with create_vault(vault_path, "password") as vault:
                vault.set("key1", "secret1")
            # Should auto-save on exit
            vault2 = create_vault(vault_path, "password")
            assert vault2.get_value("key1") == "secret1"

    def test_list_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = create_vault(Path(tmpdir) / "test.vault", "test-password")
            vault.set("key1", "value1", tags=["api"])
            vault.set("key2", "value2", tags=["db"])

            all_entries = vault.list_entries()
            assert len(all_entries) == 2

            api_entries = vault.list_entries(tag_filter=["api"])
            assert len(api_entries) == 1
            assert api_entries[0].key == "key1"

    def test_rotate_master_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / "test.vault"
            vault1 = create_vault(vault_path, "old-password")
            vault1.set("key1", "secret1")
            vault1.set("key2", "secret2")
            vault1.close()

            # Reopen and rotate
            vault2 = create_vault(vault_path, "old-password")
            vault2.rotate_master_key("new-password")
            vault2.close()

            # Verify with new password
            vault3 = create_vault(vault_path, "new-password")
            assert vault3.get_value("key1") == "secret1"
            assert vault3.get_value("key2") == "secret2"

    def test_export_import(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / "test.vault"
            vault1 = create_vault(vault_path, "password")
            vault1.set("key1", "secret1", metadata={"env": "prod"}, tags=["api"])
            vault1.set("key2", "secret2", tags=["db"])

            # Export
            exported = vault1.export_plaintext("password")
            assert exported["key1"] == "secret1"
            assert exported["key2"] == "secret2"

            # Import to new vault
            vault2 = create_vault(Path(tmpdir) / "test2.vault", "new-password")
            count = vault2.import_plaintext(exported)
            assert count == 2
            assert vault2.get_value("key1") == "secret1"
            assert vault2.get_value("key2") == "secret2"

    def test_empty_vault(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = create_vault(Path(tmpdir) / "test.vault", "password")
            assert vault.list_keys() == []
            assert vault.list_entries() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])