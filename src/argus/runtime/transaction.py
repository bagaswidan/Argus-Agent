"""Transaction & Recovery — Argus Runtime (Spec §28).

Every critical execution opens a transaction: Begin -> Checkpoint -> Commit
-> Rollback. Recovery strategies: Retry, Resume, Fallback, Abort, Replan.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TransactionStatus(StrEnum):
    ACTIVE = "active"
    CHECKPOINTED = "checkpointed"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class RecoveryStrategy(StrEnum):
    RETRY = "retry"
    RESUME = "resume"
    FALLBACK = "fallback"
    ABORT = "abort"
    REPLAN = "replan"


@dataclass
class Transaction:
    """A unit of critical execution."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    status: TransactionStatus = TransactionStatus.ACTIVE
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)
    committed_at: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def checkpoint(self, label: str, data: dict[str, Any] | None = None) -> int:
        """Record a checkpoint. Returns checkpoint index."""
        self.checkpoints.append(
            {"label": label, "data": data or {}, "time": time.monotonic()},
        )
        self.status = TransactionStatus.CHECKPOINTED
        return len(self.checkpoints) - 1

    def rollback_to(self, index: int) -> None:
        """Rollback: keep checkpoints up to index, discard the rest."""
        if 0 <= index < len(self.checkpoints):
            self.checkpoints = self.checkpoints[: index + 1]


class TransactionManager:
    """Manages transactions; each is independently recoverable."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._transactions: dict[str, Transaction] = {}
        self._recovery: list[dict[str, Any]] = []
        self._max_recovery = 500

    def begin(self, name: str = "", payload: dict[str, Any] | None = None) -> Transaction:
        tx = Transaction(name=name, payload=payload or {})
        with self._lock:
            self._transactions[tx.id] = tx
        return tx

    def get(self, tx_id: str) -> Transaction | None:
        with self._lock:
            return self._transactions.get(tx_id)

    def commit(self, tx_id: str) -> bool:
        with self._lock:
            tx = self._transactions.get(tx_id)
            if tx is None or tx.status in (TransactionStatus.COMMITTED, TransactionStatus.ROLLED_BACK):
                return False
            tx.status = TransactionStatus.COMMITTED
            tx.committed_at = time.monotonic()
            return True

    def rollback(self, tx_id: str) -> bool:
        with self._lock:
            tx = self._transactions.get(tx_id)
            if tx is None:
                return False
            tx.status = TransactionStatus.ROLLED_BACK
            return True

    def record_recovery(
        self,
        tx_id: str,
        strategy: RecoveryStrategy,
        reason: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._recovery.append(
                {
                    "tx_id": tx_id,
                    "strategy": strategy.value,
                    "reason": reason,
                    "detail": detail or {},
                    "time": time.monotonic(),
                },
            )
            if len(self._recovery) > self._max_recovery:
                self._recovery = self._recovery[-self._max_recovery:]

    def suggest_recovery(self, tx_id: str, error: str) -> RecoveryStrategy:
        """Suggest a recovery strategy based on transaction state (Spec §28)."""
        tx = self.get(tx_id)
        if tx is None:
            return RecoveryStrategy.ABORT
        if tx.checkpoints:
            return RecoveryStrategy.RESUME  # can resume from checkpoint
        if "timeout" in error.lower() or "timed out" in error.lower():
            return RecoveryStrategy.RETRY
        if "not found" in error.lower() or "unavailable" in error.lower():
            return RecoveryStrategy.FALLBACK
        return RecoveryStrategy.REPLAN

    def recovery_log(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._recovery[-limit:])

    def active_count(self) -> int:
        with self._lock:
            return sum(
                1 for t in self._transactions.values()
                if t.status in (TransactionStatus.ACTIVE, TransactionStatus.CHECKPOINTED)
            )


def create_transaction_manager() -> TransactionManager:
    return TransactionManager()
