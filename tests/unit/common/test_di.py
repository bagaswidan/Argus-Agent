"""Test DI Container — Argus Core Foundation."""
from __future__ import annotations

import pytest

from argus.common.di import Container, resolve


class DummyService:
    def __init__(self, value: int = 42):
        self.value = value


class AnotherService:
    def __init__(self, dummy: DummyService):
        self.dummy = dummy


class TestContainer:
    def test_register_singleton(self):
        container = Container()
        container.register_singleton(DummyService, lambda c: DummyService(100))
        instance1 = container.resolve(DummyService)
        instance2 = container.resolve(DummyService)
        assert instance1 is instance2
        assert instance1.value == 100

    def test_register_transient(self):
        container = Container()
        container.register_transient(DummyService, lambda c: DummyService(200))
        instance1 = container.resolve(DummyService)
        instance2 = container.resolve(DummyService)
        assert instance1 is not instance2
        assert instance1.value == 200
        assert instance2.value == 200

    def test_register_scoped(self):
        container = Container()
        container.register_scoped(DummyService, lambda c: DummyService(300))
        scope1 = container.create_scope()
        scope2 = container.create_scope()
        instance1 = scope1.resolve(DummyService)
        instance2 = scope2.resolve(DummyService)
        assert instance1 is not instance2
        assert instance1.value == 300
        assert instance2.value == 300
        scope1.dispose()
        scope2.dispose()

    def test_register_instance(self):
        container = Container()
        instance = DummyService(999)
        container.register_instance(DummyService, instance)
        resolved = container.resolve(DummyService)
        assert resolved is instance

    def test_dependency_injection(self):
        container = Container()
        container.register_singleton(DummyService, lambda c: DummyService(50))
        container.register_transient(AnotherService, lambda c: AnotherService(c.resolve(DummyService)))
        another = container.resolve(AnotherService)
        assert another.dummy.value == 50

    def test_override_in_child_scope(self):
        container = Container()
        container.register_singleton(DummyService, lambda c: DummyService(10))
        scope = container.create_scope()
        scope.register_singleton(DummyService, lambda c: DummyService(20))
        assert container.resolve(DummyService).value == 10
        assert scope.resolve(DummyService).value == 20
        scope.dispose()

    def test_unregistered_raises(self):
        container = Container()
        with pytest.raises(KeyError):
            container.resolve(DummyService)

    def test_circular_dependency_detection(self):
        container = Container()
        container.register_transient(DummyService, lambda c: c.resolve(DummyService))
        with pytest.raises(RuntimeError, match="Circular dependency"):
            container.resolve(DummyService)

    def test_is_registered(self):
        container = Container()
        assert not container.is_registered(DummyService)
        container.register_singleton(DummyService, lambda c: DummyService())
        assert container.is_registered(DummyService)

    def test_clear(self):
        container = Container()
        container.register_singleton(DummyService, lambda c: DummyService())
        container.clear()
        assert not container.is_registered(DummyService)


class TestGlobalContainer:
    def test_global_resolve(self):
        # Reset global state
        from argus.common.di import _global_container
        _global_container.clear()
        _global_container.register_singleton(DummyService, lambda c: DummyService(777))
        instance = resolve(DummyService)
        assert instance.value == 777


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
