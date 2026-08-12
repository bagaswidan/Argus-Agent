"""DI Container — Argus Core Foundation.

Lightweight dependency injection container with three lifetimes:
- Singleton: one instance per container
- Transient: new instance every resolve
- Scoped: one instance per scope (for request/workflow scope)
"""
from __future__ import annotations

import threading
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")


class ServiceLifetime(Enum):
    """Service lifetime."""

    SINGLETON = "singleton"
    TRANSIENT = "transient"
    SCOPED = "scoped"


class ServiceDescriptor:
    """Descriptor for a registered service."""

    def __init__(
        self,
        service_type: type,
        factory: Callable[[Container], Any],
        lifetime: ServiceLifetime,
        instance: Any = None,
    ):
        self.service_type = service_type
        self.factory = factory
        self.lifetime = lifetime
        self.instance = instance  # for singleton/instance


class Container:
    """Dependency injection container."""

    def __init__(self, parent: Container | None = None):
        self._services: dict[type, ServiceDescriptor] = {}
        self._parent = parent
        self._lock = threading.RLock()
        self._scoped_instances: dict[type, Any] = {}
        self._disposed = False
        self._resolving: set[type] = set()  # track resolution stack for circular detection

    # ----- registration -----

    def register_singleton(self, service_type: type[T], factory: Callable[..., T]) -> None:
        """Register a singleton service."""
        with self._lock:
            self._services[service_type] = ServiceDescriptor(
                service_type, factory, ServiceLifetime.SINGLETON,
            )

    def register_transient(self, service_type: type[T], factory: Callable[..., T]) -> None:
        """Register a transient service (new instance each resolve)."""
        with self._lock:
            self._services[service_type] = ServiceDescriptor(
                service_type, factory, ServiceLifetime.TRANSIENT,
            )

    def register_scoped(self, service_type: type[T], factory: Callable[..., T]) -> None:
        """Register a scoped service (one per scope)."""
        with self._lock:
            self._services[service_type] = ServiceDescriptor(
                service_type, factory, ServiceLifetime.SCOPED,
            )

    def register_instance(self, service_type: type[T], instance: T) -> None:
        """Register a pre-created instance as singleton."""
        with self._lock:
            desc = ServiceDescriptor(service_type, lambda _: instance, ServiceLifetime.SINGLETON)
            desc.instance = instance
            self._services[service_type] = desc

    # ----- resolution -----

    def resolve(self, service_type: type[T]) -> T:
        """Resolve a service instance."""
        with self._lock:
            if self._disposed:
                raise RuntimeError("Container has been disposed")
            return self._resolve_internal(service_type)

    def _resolve_internal(self, service_type: type[T]) -> T:
        # Check local services first
        if service_type in self._services:
            desc = self._services[service_type]
            return self._create_instance(desc, service_type)

        # Check parent
        if self._parent:
            # For scoped services, we need to create instance in THIS container (the child scope)
            # so that each scope gets its own instance
            parent_desc = self._parent._services.get(service_type)
            if parent_desc and parent_desc.lifetime == ServiceLifetime.SCOPED:
                return self._create_instance(parent_desc, service_type)
            return self._parent._resolve_internal(service_type)

        raise KeyError(f"Service {service_type.__name__} not registered")

    def _create_instance(self, desc: ServiceDescriptor, service_type: type[T]) -> T:
        # Circular dependency detection
        if service_type in self._resolving:
            raise RuntimeError(f"Circular dependency detected for {service_type.__name__}")

        self._resolving.add(service_type)
        try:
            if desc.lifetime == ServiceLifetime.SINGLETON:
                if desc.instance is None:
                    desc.instance = desc.factory(self)
                return cast("T", desc.instance)

            if desc.lifetime == ServiceLifetime.SCOPED:
                if desc.service_type not in self._scoped_instances:
                    self._scoped_instances[desc.service_type] = desc.factory(self)
                return cast("T", self._scoped_instances[desc.service_type])

            # TRANSIENT
            return cast("T", desc.factory(self))
        finally:
            self._resolving.discard(service_type)

    # ----- scope -----

    def create_scope(self) -> Container:
        """Create a child scope for scoped services."""
        return Container(parent=self)

    def dispose(self) -> None:
        """Dispose scoped instances."""
        with self._lock:
            for instance in self._scoped_instances.values():
                if hasattr(instance, "close"):
                    instance.close()
                elif hasattr(instance, "__aexit__"):
                    pass  # async not handled here
            self._scoped_instances.clear()
            self._disposed = True

    # ----- utilities -----

    def is_registered(self, service_type: type) -> bool:
        """Check if service is registered in this container (not parent)."""
        return service_type in self._services

    def clear(self) -> None:
        """Clear all registrations."""
        with self._lock:
            self._services.clear()
            self._scoped_instances.clear()
            self._disposed = False


# Global container
_global_container = Container()


def get_global_container() -> Container:
    """Get global container."""
    return _global_container


def resolve[T](service_type: type[T]) -> T:
    """Resolve from global container."""
    return _global_container.resolve(service_type)


def register_singleton[T](service_type: type[T], factory: Callable[..., T]) -> None:
    """Register singleton in global container."""
    _global_container.register_singleton(service_type, factory)


def register_transient[T](service_type: type[T], factory: Callable[..., T]) -> None:
    """Register transient in global container."""
    _global_container.register_transient(service_type, factory)


def register_scoped[T](service_type: type[T], factory: Callable[..., T]) -> None:
    """Register scoped in global container."""
    _global_container.register_scoped(service_type, factory)


def register_instance[T](service_type: type[T], instance: T) -> None:
    """Register instance in global container."""
    _global_container.register_instance(service_type, instance)
