"""Test Extension — Argus."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from argus.extension.manager import (
    ExtensionState,
    create_extension_manager,
)
from argus.extension.manifest import (
    ExtensionManifest,
    ExtensionType,
    ManifestValidationError,
    load_manifest,
)
from argus.extension.rpc import ExtensionRpc, create_rpc_response


def make_manifest(**overrides) -> ExtensionManifest:
    base = dict(
        extension_id="ext.test",
        name="Test Extension",
        version="1.0.0",
        author="tester",
        type=ExtensionType.CAPABILITY,
        entry_point="test_ext.py",
        capabilities=["test.cap"],
        permissions=["execute"],
    )
    base.update(overrides)
    return ExtensionManifest.from_dict(base)


class TestManifest:
    def test_valid_manifest(self):
        m = make_manifest()
        m.validate()  # no raise

    def test_missing_id(self):
        with pytest.raises(ManifestValidationError):
            make_manifest(extension_id="").validate()

    def test_missing_name(self):
        with pytest.raises(ManifestValidationError):
            make_manifest(name="").validate()

    def test_missing_version(self):
        with pytest.raises(ManifestValidationError):
            make_manifest(version="").validate()

    def test_missing_author(self):
        with pytest.raises(ManifestValidationError):
            make_manifest(author="").validate()

    def test_bad_semver(self):
        with pytest.raises(ManifestValidationError):
            make_manifest(min_core_version="abc").validate()

    def test_to_dict_roundtrip(self):
        m = make_manifest()
        m2 = ExtensionManifest.from_dict(m.to_dict())
        assert m2.extension_id == m.extension_id
        assert m2.type == ExtensionType.CAPABILITY

    def test_load_manifest_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "manifest.json"
            p.write_text(json.dumps(make_manifest().to_dict()))
            m = load_manifest(p)
            assert m.name == "Test Extension"

    def test_load_manifest_missing_file(self):
        with pytest.raises(ManifestValidationError):
            load_manifest("/nonexistent/manifest.json")


class TestRpc:
    def test_rpc_response_ok(self):
        r = create_rpc_response(status="ok", evidence=["e1"], metrics={"m": 1.0})
        assert r.ok is True
        assert r.evidence == ["e1"]

    def test_rpc_response_error(self):
        r = create_rpc_response(status="error", error={"code": "X"})
        assert r.ok is False

    def test_contract_methods_abstract(self):
        class Impl(ExtensionRpc):
            def execute(self, params):
                return create_rpc_response(data=params)

        impl = Impl()
        with pytest.raises(NotImplementedError):
            impl.initialize()
        assert impl.execute({"a": 1}).data == {"a": 1}


# --- Fixture extension module ---

_TEST_EXT = """
from argus.extension.rpc import ExtensionRpc, create_rpc_response

class TestExtension(ExtensionRpc):
    def __init__(self):
        self.configured = {}

    def initialize(self, config=None):
        return create_rpc_response(status="ok", evidence=["initialized"])

    def execute(self, params):
        return create_rpc_response(status="ok", data={"echo": params}, metrics={"dur": 1.5})

    def health(self):
        return create_rpc_response(status="ok", evidence=["alive"])

    def configure(self, config):
        self.configured = config
        return create_rpc_response(status="ok", evidence=["configured"])

    def shutdown(self):
        return create_rpc_response(status="ok")
"""


@pytest.fixture()
def manager_with_ext(tmp_path):
    # Write extension module
    ext_dir = tmp_path / "ext.test"
    ext_dir.mkdir()
    (ext_dir / "test_ext.py").write_text(_TEST_EXT)

    mgr = create_extension_manager()
    mgr.add_load_dir(tmp_path)
    mgr.install(make_manifest())
    return mgr, ext_dir


class TestExtensionManager:
    def test_install_sets_validated(self, tmp_path):
        mgr = create_extension_manager()
        mgr.install(make_manifest())
        assert mgr.state("ext.test") == ExtensionState.VALIDATED

    def test_duplicate_install_raises(self, tmp_path):
        mgr = create_extension_manager()
        mgr.install(make_manifest())
        with pytest.raises(ManifestValidationError):
            mgr.install(make_manifest())

    def test_full_lifecycle(self, manager_with_ext):
        mgr, ext_dir = manager_with_ext
        assert mgr.load("ext.test") is True
        assert mgr.state("ext.test") == ExtensionState.LOADED

        resp = mgr.initialize("ext.test")
        assert resp.ok is True
        assert mgr.state("ext.test") == ExtensionState.READY

        exec_resp = mgr.execute("ext.test", {"q": 1})
        assert exec_resp.ok is True
        assert exec_resp.data == {"echo": {"q": 1}}

        assert mgr.health("ext.test").ok is True
        assert mgr.unload("ext.test") is True
        assert mgr.state("ext.test") == ExtensionState.UNLOADED

    def test_execute_before_load_raises(self, manager_with_ext):
        mgr, _ = manager_with_ext
        with pytest.raises(ManifestValidationError):
            mgr.execute("ext.test", {})

    def test_remove(self, manager_with_ext):
        mgr, _ = manager_with_ext
        mgr.load("ext.test")
        assert mgr.remove("ext.test") is True
        assert mgr.get("ext.test") is None

    def test_reload(self, manager_with_ext):
        mgr, _ = manager_with_ext
        mgr.load("ext.test")
        mgr.initialize("ext.test")
        assert mgr.reload("ext.test") is True
        assert mgr.state("ext.test") == ExtensionState.UPDATED

    def test_list_extensions(self, manager_with_ext):
        mgr, _ = manager_with_ext
        assert len(mgr.list_extensions()) == 1

    def test_crash_isolated(self, manager_with_ext):
        """Crash in execute must not stop the manager from serving others."""
        mgr, _ = manager_with_ext
        mgr.load("ext.test")
        # Monkeypatch instance to raise
        mgr._instances["ext.test"].execute = lambda p: (_ for _ in ()).throw(RuntimeError("boom"))
        resp = mgr.execute("ext.test", {})
        assert resp.ok is False
        assert resp.error["code"] == "EXEC_FAILED"
        # Manager still usable
        assert mgr.health("ext.test").ok is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
