"""Request and result shapes that every chat and embedding provider shares."""

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

from trialscribe_worker.utils.constant import MAX_IDEMPOTENCY_KEY_LENGTH, MIN_IDEMPOTENCY_KEY_LENGTH


class ChatMessage(BaseModel):
    """One turn in a chat completion."""

    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """One chat completion the gateway is asked to run."""

    messages: list[ChatMessage]
    model: str
    organization_id: UUID
    conversation_id: UUID | None
    job_id: UUID | None
    account_id: UUID | None
    idempotency_key: str = Field(
        min_length=MIN_IDEMPOTENCY_KEY_LENGTH,
        max_length=MAX_IDEMPOTENCY_KEY_LENGTH,
    )
    thinking: bool = False


class ChatResult(BaseModel):
    """What a chat provider returns after one completion."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_hit_tokens: int
    latency_ms: int


class EmbeddingRequest(BaseModel):
    """One embedding batch the gateway is asked to run."""

    texts: list[str]
    model: str
    organization_id: UUID
    conversation_id: UUID | None
    job_id: UUID | None
    account_id: UUID | None
    idempotency_key: str = Field(
        min_length=MIN_IDEMPOTENCY_KEY_LENGTH,
        max_length=MAX_IDEMPOTENCY_KEY_LENGTH,
    )


class EmbeddingResult(BaseModel):
    """What an embedding provider returns after one batch."""

    vectors: list[list[float]]
    model: str
    dimensions: int
    input_tokens: int
    latency_ms: int


class ChatProvider(Protocol):
    """A chat completion backend."""

    async def complete(self, request: ChatRequest) -> ChatResult: ...


class EmbeddingProvider(Protocol):
    """An embedding backend."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...
