"""Compatibility exports for AI-engine runtime settings."""

import os

from dotenv import load_dotenv

from trialscribe_ai.utils.constant import (
    ALLOWED_WEBSITES_FILE,
    CONFIG_DIR,
    DEFAULT_K_VALUE,
    DEFAULT_MAX_RESULTS,
    DEFAULT_NUM_WORDS,
)

load_dotenv()

MAX_RESULTS = int(os.getenv("MAX_RESULTS", str(DEFAULT_MAX_RESULTS)))
K_VALUE = int(os.getenv("K_value", str(DEFAULT_K_VALUE)))
NUM_WORDS = int(os.getenv("NUM_WORDS", str(DEFAULT_NUM_WORDS)))

__all__ = [
    "ALLOWED_WEBSITES_FILE",
    "CONFIG_DIR",
    "K_VALUE",
    "MAX_RESULTS",
    "NUM_WORDS",
]
