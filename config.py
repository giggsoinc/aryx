"""Repo-root re-export of the raven-log wrapper.

The implementation lives in ``aryx.raven_log_config`` so it is part of the
installed package (a wheel does not ship this file). Aryx code imports it from
there; this module only exists for tooling that follows the Raven
``from config import log`` convention.
"""
from aryx.raven_log_config import log  # noqa: F401
