"""Resource limit test — Argus sandbox resource caps."""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from argus.runtime.sandbox import ResourceLimit


class TestResourceLimit:
    """Assert ResourceLimit sets cgroup-style bounds."""

    def test_io_limit(self, tmp_path):
        limit = ResourceLimit(max_output_bytes=1024)
        assert limit.max_output_bytes == 1024

    def test_cpu_limit(self):
        limit = ResourceLimit(max_cpu_seconds=2)
        assert limit.max_cpu_seconds == 2

    def test_memory_limit(self):
        limit = ResourceLimit(max_memory_mb=256)
        assert limit.max_memory_mb == 256

    def test_files_limit(self):
        limit = ResourceLimit(max_files=5)
        assert limit.max_files == 5

    def test_network_default_off(self):
        limit = ResourceLimit()
        assert limit.allow_network is False

    def test_network_relaxed(self):
        from argus.runtime.sandbox import ResourceLimit
        limit = ResourceLimit.relaxed()
        assert limit.allow_network is True

    def test_filesystem_write_default_off(self):
        limit = ResourceLimit()
        assert limit.allow_fs_write is False

    def test_filesystem_write_relaxed(self):
        from argus.runtime.sandbox import ResourceLimit
        limit = ResourceLimit.relaxed()
        assert limit.allow_fs_write is True
