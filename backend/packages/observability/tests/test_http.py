from uuid import UUID

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from trialscribe_observability.http import instrument_app

ITEM_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
FORBIDDEN_LABELS = frozenset(
    {"organization_id", "conversation_id", "job_id", "account_id"}
)


async def read_item(request: Request) -> JSONResponse:
    return JSONResponse({"id": request.path_params["item_id"]})


def _label_names(body: str) -> set[str]:
    names: set[str] = set()
    for line in body.splitlines():
        if line.startswith("#") or "{" not in line:
            continue
        start = line.index("{")
        end = line.index("}", start)
        for pair in line[start + 1 : end].split(","):
            key = pair.split("=", 1)[0].strip()
            if key:
                names.add(key)
    return names


def test_metrics_use_the_route_template_not_the_raw_id() -> None:
    app = Starlette(routes=[Route("/items/{item_id}", read_item)])
    instrument_app(app, service="test-service")
    client = TestClient(app)

    item = client.get(f"/items/{ITEM_ID}")
    metrics = client.get("/metrics")

    assert item.status_code == 200
    assert metrics.status_code == 200
    body = metrics.text
    assert "trialscribe_http_requests_total" in body
    assert "trialscribe_http_request_duration_seconds" in body
    assert 'handler="/items/{item_id}"' in body
    assert 'service="test-service"' in body
    assert str(ITEM_ID) not in body
    assert FORBIDDEN_LABELS.isdisjoint(_label_names(body))
