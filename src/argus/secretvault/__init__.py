"""SecretVault — Argus Phase 2.

Secure secret storage with encryption for API keys, tokens, credentials.
"""
from __future__ import annotations

from argus.secretvault.vault import SecretVault, VaultConfig, SecretEntry

__all__ = ["SecretVault", "VaultConfig", "SecretEntry"]