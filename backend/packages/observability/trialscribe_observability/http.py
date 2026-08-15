"""HTTP request metrics and the /metrics scrape page."""

from time import monotonic
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

HTTP_REQUESTS_TOTAL = Counter(
    "trialscribe_http_requests_total",
    "HTTP requests handled by a TrialScribe service",
    ["service", "method", "handler", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "trialscribe_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["service", "method", "handler"],
)

UNMATCHED_HANDLER = "unmatched"


def _route_template(candidate: object) -> str | None:
    for attr in ("path", "path_format"):
        value = getattr(candidate, attr, None)
        if isinstance(value, str) and value:
            return value
    return None


def _handler_from_scope(scope: Scope) -> str:
    template = _route_template(scope.get("route"))
    if template is not None:
        return template
    endpoint = scope.get("endpoint")
    router = scope.get("router")
    routes = getattr(router, "routes", ())
    for candidate in routes:
        if getattr(candidate, "endpoint", None) is endpoint:
            template = _route_template(candidate)
            if template is not None:
                return template
    return UNMATCHED_HANDLER


class MetricsMiddleware:
    """Count each request with a bounded route template, never a raw URL."""

    def __init__(self, app: ASGIApp, *, service: str) -> None:
        self.app = app
        self._service = service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = monotonic()
        status_code = 500

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            handler = _handler_from_scope(scope)
            try:
                HTTP_REQUESTS_TOTAL.labels(
                    service=self._service,
                    method=scope.get("method", "GET"),
                    handler=handler,
                    status=str(status_code),
                ).inc()
                HTTP_REQUEST_DURATION_SECONDS.labels(
                    service=self._service,
                    method=scope.get("method", "GET"),
                    handler=handler,
                ).observe(monotonic() - started)
            except Exception:
                pass


async def metrics_endpoint(_request: Request) -> Response:
    """Return the current process registry in Prometheus text format."""

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def instrument_app(app: Starlette, *, service: str) -> None:
    """Attach request metrics and GET /metrics to one Starlette or FastAPI app."""

    app.add_middleware(MetricsMiddleware, service=service)
    app.add_route("/metrics", metrics_endpoint, methods=["GET"])
