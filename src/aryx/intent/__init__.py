"""User Intent Capture (C01): deterministic front-door for dashboard requests.

Collects the business domain, plain-language objective, and optional dashboard
preferences, then validates and versions them into a `user_intent` object with a
correlation id. No LLM — required fields block, unsupported catalogue values are
retained as warnings.
"""

from aryx.intent.capture import capture_intent
from aryx.intent.models import (
    DateRange,
    IntentPreferences,
    UserIntent,
    UserIntentRequest,
)

__all__ = [
    "capture_intent",
    "DateRange",
    "IntentPreferences",
    "UserIntent",
    "UserIntentRequest",
]
