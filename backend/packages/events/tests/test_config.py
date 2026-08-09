import pytest
from pydantic import ValidationError

from trialscribe_events.config import EventBusSettings


def test_defaults_apply_around_the_required_broker_list() -> None:
    settings = EventBusSettings(bootstrap_servers="localhost:9092")

    assert settings.bootstrap_servers == "localhost:9092"
    assert settings.topic_prefix == "trialscribe"
    assert settings.topic_partitions == 3
    assert settings.topic_replication_factor == 1
    assert settings.max_delivery_attempts == 3
    assert settings.retry_backoff_seconds == 0.5
    assert settings.retry_backoff_cap_seconds == 8.0
    assert settings.request_timeout_ms() == 10000


def test_settings_load_the_documented_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVENTS_BOOTSTRAP_SERVERS", " kafka:29092 , localhost:9092 ")
    monkeypatch.setenv("EVENTS_TOPIC_PREFIX", "trialscribe-test")
    monkeypatch.setenv("EVENTS_CLIENT_ID", "worker-service")
    monkeypatch.setenv("EVENTS_CONSUMER_GROUP", "worker-events")
    monkeypatch.setenv("EVENTS_MAX_DELIVERY_ATTEMPTS", "5")

    settings = EventBusSettings()

    assert settings.bootstrap_servers == "kafka:29092,localhost:9092"
    assert settings.topic_prefix == "trialscribe-test"
    assert settings.client_id == "worker-service"
    assert settings.consumer_group == "worker-events"
    assert settings.max_delivery_attempts == 5


def test_settings_require_no_secret_material() -> None:
    assert "password" not in EventBusSettings.model_fields
    assert "secret" not in EventBusSettings.model_fields


@pytest.mark.parametrize(
    "bootstrap_servers",
    ["", "   ", ",", "localhost", "localhost:", ":9092", "localhost:not-a-port"],
)
def test_rejects_broker_lists_that_are_not_host_port_pairs(bootstrap_servers: str) -> None:
    with pytest.raises(ValidationError) as error:
        EventBusSettings(bootstrap_servers=bootstrap_servers)

    assert "comma-separated host:port list" in str(error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("topic_prefix", ""),
        ("topic_partitions", 0),
        ("topic_replication_factor", 0),
        ("max_delivery_attempts", 0),
        ("retry_backoff_seconds", 0),
        ("retry_backoff_cap_seconds", 0),
        ("request_timeout_seconds", 0),
    ],
)
def test_rejects_values_outside_the_documented_bounds(field: str, value: object) -> None:
    values: dict[str, object] = {"bootstrap_servers": "localhost:9092", field: value}

    with pytest.raises(ValidationError):
        EventBusSettings(**values)
