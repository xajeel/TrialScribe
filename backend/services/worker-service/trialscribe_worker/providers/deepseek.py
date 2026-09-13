"""DeepSeek chat completions through the OpenAI-compatible SDK."""

from time import monotonic
from typing import Any, Protocol

import httpx
import openai

from trialscribe_worker.providers.types import ChatRequest, ChatResult
from trialscribe_worker.utils.exceptions import (
    ProviderConfigError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class CompletionsAPI(Protocol):
    async def create(self, **kwargs: Any) -> Any: ...


class ChatAPI(Protocol):
    completions: CompletionsAPI


class OpenAICompatibleClient(Protocol):
    chat: ChatAPI


class DeepSeekChatProvider:
    """One DeepSeek chat completion, with thinking turned off."""

    def __init__(self, client: OpenAICompatibleClient, model: str) -> None:
        self._client = client
        self._model = model

    async def complete(self, request: ChatRequest) -> ChatResult:
        """Call DeepSeek and map transport failures onto provider errors."""

        started = monotonic()
        try:
            response = await self._client.chat.completions.create(
                model=request.model or self._model,
                messages=[
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ],
                extra_body={"thinking": {"type": "disabled"}},
            )
        except (openai.APITimeoutError, httpx.TimeoutException) as error:
            raise ProviderTimeoutError from error
        except openai.RateLimitError as error:
            raise ProviderRateLimitedError from error
        except openai.APIStatusError as error:
            raise _status_error(error) from error
        except httpx.HTTPStatusError as error:
            raise _http_status_error(error) from error

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ProviderUnavailableError
        message = getattr(choices[0], "message", None)
        text = getattr(message, "content", None) or ""
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        details = getattr(usage, "prompt_tokens_details", None)
        cache_hit_tokens = int(getattr(details, "cached_tokens", 0) or 0)
        return ChatResult(
            text=text,
            model=request.model or self._model,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            cache_hit_tokens=cache_hit_tokens,
            latency_ms=max(0, int((monotonic() - started) * 1000)),
        )


def _status_error(error: openai.APIStatusError) -> Exception:
    status = getattr(error, "status_code", None)
    if status == 429:
        return ProviderRateLimitedError()
    if isinstance(status, int) and status >= 500:
        return ProviderUnavailableError()
    return ProviderConfigError()


def _http_status_error(error: httpx.HTTPStatusError) -> Exception:
    status = error.response.status_code if error.response is not None else 0
    if status == 429:
        return ProviderRateLimitedError()
    if status >= 500:
        return ProviderUnavailableError()
    return ProviderConfigError()
