"""Versioned model identity, dimensions, and integer-micro prices."""

from dataclasses import dataclass

from trialscribe_worker.utils.constant import PRICING_VERSION_DEFAULT
from trialscribe_worker.utils.exceptions import ProviderConfigError


@dataclass(frozen=True, slots=True)
class ModelRates:
    """How many USD micros one million tokens of each kind cost."""

    input_miss_micros_per_million: int
    input_hit_micros_per_million: int
    output_micros_per_million: int


PRICING_TABLES: dict[str, dict[str, ModelRates]] = {
    PRICING_VERSION_DEFAULT: {
        "deepseek-v4-flash": ModelRates(140000, 2800, 280000),
        "deepseek-v4-pro": ModelRates(435000, 3625, 870000),
        "BAAI/bge-small-en-v1.5": ModelRates(0, 0, 0),
        "fake-chat": ModelRates(100000, 0, 200000),
        "fake-embed": ModelRates(0, 0, 0),
    }
}


def cost_micros(
    model: str,
    version: str,
    input_tokens: int,
    output_tokens: int,
    cache_hit_tokens: int = 0,
) -> int:
    """Return integer USD micros for one call. Never uses floating-point money."""

    table = PRICING_TABLES.get(version)
    if table is None:
        raise ProviderConfigError
    rates = table.get(model)
    if rates is None:
        raise ProviderConfigError
    miss_tokens = max(input_tokens - cache_hit_tokens, 0)
    return (
        miss_tokens * rates.input_miss_micros_per_million
        + cache_hit_tokens * rates.input_hit_micros_per_million
        + output_tokens * rates.output_micros_per_million
    ) // 1_000_000
