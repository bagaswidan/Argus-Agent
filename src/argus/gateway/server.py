"""Gateway Server — Argus.

HTTP server for the gateway with REST API, WebSocket support, and adapter integration.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
    WebApplication = web.Application
    WebAppRunner = web.AppRunner
    WebTCPSite = web.TCPSite
    WebRequest = web.Request
    WebResponse = web.Response
    WebMiddleware = web.middleware
except ImportError:
    AIOHTTP_AVAILABLE = False
    WebApplication = object
    WebAppRunner = object
    WebTCPSite = object
    WebRequest = object
    WebResponse = object
    WebMiddleware = lambda f: f  # no-op decorator when aiohttp not available

from argus.gateway.auth import AuthManager, TokenData
from argus.gateway.adapters import (
    PlatformAdapter,
    PlatformMessage,
    PlatformResponse,
    PlatformType,
    adapter_registry,
    create_adapter,
)


logger = logging.getLogger(__name__)


@dataclass
class GatewayConfig:
    """Gateway server configuration."""

    host: str = "0.0.0.0"
    port: int = 8080
    auth: Optional[AuthManager] = None
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    max_message_size: int = 1024 * 1024  # 1MB
    request_timeout: int = 30


class GatewayServer:
    """HTTP gateway server with adapter support."""

    def __init__(
        self,
        config: Optional[GatewayConfig] = None,
        message_handler: Optional[Callable[[PlatformMessage], Any]] = None,
    ):
        self.config = config or GatewayConfig()
        self.message_handler = message_handler
        self.auth = self.config.auth or AuthManager()
        self._app: Optional[WebApplication] = None
        self._runner: Optional[WebAppRunner] = None
        self._site: Optional[WebTCPSite] = None
        self._adapters: dict[PlatformType, PlatformAdapter] = {}
        self._adapters_lock = asyncio.Lock()
        self._running = False

    async def start(self) -> None:
        """Start the gateway server."""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp not installed. Install with: pip install aiohttp")

        if self._running:
            return

        self._app = web.Application(
            client_max_size=self.config.max_message_size,
        )

        # Setup routes
        self._app.router.add_get("/health", self._health_check)
        self._app.router.add_post("/api/v1/messages", self._handle_message)
        self._app.router.add_get("/api/v1/adapters", self._list_adapters)
        self._app.router.add_post("/api/v1/adapters/{platform}/connect", self._connect_adapter)
        self._app.router.add_post("/api/v1/adapters/{platform}/disconnect", self._disconnect_adapter)
        self._app.router.add_post("/api/v1/auth/token", self._create_token)
        self._app.router.add_get("/api/v1/auth/verify", self._verify_token)

        # CORS middleware
        self._app.middlewares.append(self._cors_middleware)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.config.host, self.config.port)
        await self._site.start()

        self._running = True
        logger.info(f"Gateway server started on {self.config.host}:{self.config.port}")

    async def stop(self) -> None:
        """Stop the gateway server."""
        if not self._running:
            return

        # Disconnect all adapters
        for adapter in self._adapters.values():
            try:
                await adapter.disconnect()
            except Exception:
                logger.exception("Error while disconnecting adapter during shutdown")
        self._adapters.clear()

        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

        self._running = False
        logger.info("Gateway server stopped")

    async def add_adapter(self, platform_type: PlatformType, config: dict[str, Any]) -> bool:
        """Add and connect a platform adapter."""
        adapter = create_adapter(platform_type, config)
        if not adapter:
            return False

        if self.message_handler:
            adapter.set_message_handler(self.message_handler)

        success = await adapter.connect()
        if not success:
            return False

        async with self._adapters_lock:
            if platform_type in self._adapters:
                # Another adapter already registered concurrently.
                try:
                    await adapter.disconnect()
                except Exception:
                    pass
                return False
            self._adapters[platform_type] = adapter

        logger.info(f"Connected adapter: {platform_type.value}")
        return True

    async def remove_adapter(self, platform_type: PlatformType) -> bool:
        """Remove and disconnect a platform adapter."""
        async with self._adapters_lock:
            adapter = self._adapters.get(platform_type)
            if not adapter:
                return False

        try:
            await adapter.disconnect()
        except Exception:
            logger.exception("Error disconnecting adapter %s", platform_type.value)

        async with self._adapters_lock:
            # Remove only if the same adapter is still registered.
            if self._adapters.get(platform_type) is adapter:
                del self._adapters[platform_type]
                return True
        return False

    async def broadcast(self, response: PlatformResponse, platforms: Optional[list[PlatformType]] = None) -> dict[PlatformType, bool]:
        """Send a message to multiple platforms."""
        async with self._adapters_lock:
            targets = platforms if platforms is not None else list(self._adapters.keys())
            adapters = {pt: self._adapters.get(pt) for pt in targets}
        results = {}
        for platform_type, adapter in adapters.items():
            if adapter:
                try:
                    results[platform_type] = await adapter.send_message(response)
                except Exception:
                    logger.exception("Error broadcasting to %s", platform_type.value)
                    results[platform_type] = False
            else:
                results[platform_type] = False
        return results

    @property
    def is_running(self) -> bool:
        return self._running

    # --- Route handlers ---

    async def _health_check(self, request: WebRequest) -> WebResponse:
        adapters_status = {}
        async with self._adapters_lock:
            adapters_status = {
                k.value: v.is_connected for k, v in self._adapters.items()
            }
        return web.json_response({
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "adapters": adapters_status,
        })

    async def _handle_message(self, request: WebRequest) -> WebResponse:
        # Auth check
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            token_data = self.auth.verify_token(token)
            if not token_data:
                return web.json_response({"error": "Invalid token"}, status=401)
        elif not self.config.auth:  # No auth configured, allow
            token_data = TokenData(sub="anonymous", scopes=["*"])
        else:
            return web.json_response({"error": "Missing authorization"}, status=401)

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        # Validate required fields
        required = ["platform", "chat_id", "text"]
        for field in required:
            if field not in data:
                return web.json_response({"error": f"Missing field: {field}"}, status=400)

        try:
            platform = PlatformType(data["platform"])
        except ValueError:
            return web.json_response({"error": f"Unknown platform: {data['platform']}"}, status=400)

        adapter = self._adapters.get(platform)
        if not adapter:
            return web.json_response({"error": f"Adapter not connected: {platform.value}"}, status=400)

        response = PlatformResponse(
            chat_id=data["chat_id"],
            text=data["text"],
            reply_to_message_id=data.get("reply_to_message_id"),
            parse_mode=data.get("parse_mode"),
            metadata=data.get("metadata", {}),
        )

        success = await adapter.send_message(response)
        return web.json_response({"success": success})

    async def _list_adapters(self, request: WebRequest) -> WebResponse:
        async with self._adapters_lock:
            adapters_snapshot = list(self._adapters.items())
        return web.json_response({
            "adapters": [
                {
                    "platform": p.value,
                    "connected": a.is_connected,
                    "platform_name": a.platform_name,
                }
                for p, a in adapters_snapshot
            ],
            "available": [p.value for p in adapter_registry.list_registered()],
        })

    async def _connect_adapter(self, request: WebRequest) -> WebResponse:
        platform_str = request.match_info["platform"]
        try:
            platform = PlatformType(platform_str)
        except ValueError:
            return web.json_response({"error": f"Unknown platform: {platform_str}"}, status=400)

        try:
            config = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        success = await self.add_adapter(platform, config)
        return web.json_response({"success": success, "platform": platform.value})

    async def _disconnect_adapter(self, request: WebRequest) -> WebResponse:
        platform_str = request.match_info["platform"]
        try:
            platform = PlatformType(platform_str)
        except ValueError:
            return web.json_response({"error": f"Unknown platform: {platform_str}"}, status=400)

        success = await self.remove_adapter(platform)
        return web.json_response({"success": success, "platform": platform.value})

    async def _create_token(self, request: WebRequest) -> WebResponse:
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        sub = data.get("sub")
        if not sub:
            return web.json_response({"error": "Missing 'sub'"}, status=400)

        scopes = data.get("scopes", [])
        ttl = data.get("ttl_seconds")
        extra = data.get("extra")

        token = self.auth.create_token(sub, scopes, ttl, extra)
        return web.json_response({"token": token})

    async def _verify_token(self, request: WebRequest) -> WebResponse:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return web.json_response({"valid": False, "error": "Missing bearer token"}, status=401)

        token = auth_header[7:]
        token_data = self.auth.verify_token(token)

        if token_data:
            return web.json_response({"valid": True, "token_data": token_data.to_dict()})
        else:
            return web.json_response({"valid": False, "error": "Invalid or expired token"}, status=401)

    @WebMiddleware
    async def _cors_middleware(self, request: WebRequest, handler):
        origin = request.headers.get("Origin", "")
        if request.method == "OPTIONS":
            # Handle CORS preflight
            if self.config.cors_origins == ["*"] or origin in self.config.cors_origins:
                return web.Response(
                    status=200,
                    headers={
                        "Access-Control-Allow-Origin": origin or "*",
                        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    },
                )
            else:
                return web.Response(status=200)

        response = await handler(request)
        if self.config.cors_origins == ["*"] or origin in self.config.cors_origins:
            response.headers["Access-Control-Allow-Origin"] = origin or "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response


def create_gateway_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    message_handler: Optional[Callable[[PlatformMessage], Any]] = None,
) -> GatewayServer:
    """Factory function to create a gateway server."""
    config = GatewayConfig(host=host, port=port)
    return GatewayServer(config=config, message_handler=message_handler)
