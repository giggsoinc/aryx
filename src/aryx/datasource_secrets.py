"""Fernet-symmetric secret store for datasource credentials (Slice 2).

Key comes from the ARYX_SECRET_KEY environment variable (URL-safe base64,
32 bytes raw). In dev, if the env var is missing, the module derives a
deterministic key from the machine and logs a loud warning — DO NOT ship
that path to prod. Plaintext NEVER leaves this module; responses contain
only the mask (last-4 of SHA256(plaintext)).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import socket

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_DEV_KEY_WARNING_ONCE = False


def _load_key() -> bytes:
    """Return the Fernet key bytes; warn once if falling back to a dev key."""
    raw = os.environ.get("ARYX_SECRET_KEY", "").strip()
    if raw:
        return raw.encode()
    global _DEV_KEY_WARNING_ONCE
    if not _DEV_KEY_WARNING_ONCE:
        logger.warning(
            "ARYX_SECRET_KEY unset — using machine-derived dev key. DO NOT "
            "use this in production: encrypted secrets are not portable.")
        _DEV_KEY_WARNING_ONCE = True
    seed = f"aryx-dev::{socket.gethostname()}".encode()
    return base64.urlsafe_b64encode(hashlib.sha256(seed).digest())


def _fernet() -> Fernet:
    return Fernet(_load_key())


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext credential. Empty input returns empty output."""
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a stored credential; raises ValueError on a wrong key."""
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Secret decrypt failed — ARYX_SECRET_KEY mismatch."
        ) from exc


def mask(plaintext: str) -> str:
    """Return a non-reversible 'last-4 of sha256' tag for UI display.

    Stable so the same secret yields the same mask, but reveals nothing
    about the plaintext itself.
    """
    if not plaintext:
        return ""
    digest = hashlib.sha256(plaintext.encode()).hexdigest()
    return f"••••{digest[-4:]}"


def key_is_configured() -> bool:
    """True iff ARYX_SECRET_KEY is set in the environment."""
    return bool(os.environ.get("ARYX_SECRET_KEY", "").strip())
