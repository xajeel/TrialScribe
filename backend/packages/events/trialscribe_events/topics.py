"""Deliberate topic provisioning, so no topic is created by accident."""

from collections.abc import Sequence

from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError

from trialscribe_events.config import EventBusSettings
from trialscribe_events.registry import dead_letter_topic
from trialscribe_events.utils.exceptions import EventError

TOPIC_ALREADY_EXISTS_CODE = 36
NO_ERROR_CODE = 0
PROVISION_FAILURE_MESSAGE = "event topics could not be provisioned"


def desired_topics(topic_names: Sequence[str]) -> tuple[str, ...]:
    """Return each topic together with the dead-letter topic that shadows it."""

    names: list[str] = []
    for topic in topic_names:
        for name in (topic, dead_letter_topic(topic)):
            if name not in names:
                names.append(name)
    return tuple(names)


def check_topic_errors(response: object) -> None:
    """Reject any create-topic outcome other than success or already-exists."""

    for entry in getattr(response, "topic_errors", ()):
        error_code = entry[1]
        if error_code in (NO_ERROR_CODE, TOPIC_ALREADY_EXISTS_CODE):
            continue
        raise EventError(PROVISION_FAILURE_MESSAGE)


async def ensure_topics(
    settings: EventBusSettings,
    topic_names: Sequence[str],
    *,
    admin_client: AIOKafkaAdminClient | None = None,
) -> tuple[str, ...]:
    """Create every missing topic and its dead-letter companion; return the created names."""

    names = desired_topics(topic_names)
    if not names:
        return ()

    admin = admin_client or AIOKafkaAdminClient(
        bootstrap_servers=settings.bootstrap_servers,
        client_id=settings.client_id,
        request_timeout_ms=settings.request_timeout_ms(),
    )
    await admin.start()
    try:
        existing = set(await admin.list_topics())
        missing = [name for name in names if name not in existing]
        if not missing:
            return ()
        new_topics = [
            NewTopic(
                name,
                num_partitions=settings.topic_partitions,
                replication_factor=settings.topic_replication_factor,
            )
            for name in missing
        ]
        try:
            check_topic_errors(await admin.create_topics(new_topics))
        except TopicAlreadyExistsError:
            return ()
        return tuple(missing)
    finally:
        await admin.close()
