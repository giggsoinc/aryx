"""Turn raw driver/SQLAlchemy connection errors into plain-English messages.

Users connecting a database see the returned string directly, so it must
say what to check (firewall, password, host name…) rather than echo a
psycopg traceback — and it must never contain the password.
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus

# (regex searched in the lower-cased raw error, message template). First
# match wins, so the specific patterns sit above the broad network ones.
_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"password authentication failed|access denied for user|ora-01017"
                r"|invalid username/password|fe_sendauth"),
     "Username or password is wrong — check the Username and Password fields."),
    (re.compile(r"permission denied for database|ora-01045"),
     ("User doesn't have permission to connect to database '{database}' — ask "
      "the database admin to grant CONNECT on it.")),
    (re.compile(r'database "[^"]*" does not exist|unknown database|ora-12514'),
     "Database '{database}' doesn't exist on {target} — check the Database name."),
    (re.compile(r"failed to resolve host|name or service not known"
                r"|could not translate host name|nodename nor servname"
                r"|getaddrinfo failed|unknown host"),
     "Host '{host}' could not be found — check the Host field for typos."),
    (re.compile(r"no pg_hba\.conf entry"),
     ("The database at {target} refused this machine's IP address — ask the "
      "database admin to allow it (pg_hba.conf / allow-list).")),
    (re.compile(r"timeout expired|timed out|server closed the connection unexpectedly"
                r"|connection refused|no route to host|network is unreachable"
                r"|can't connect to mysql server|ora-12170|ora-12541"),
     ("Can't reach the database at {target} — the server didn't respond. "
      "Check that it is running, the port is right, and that its firewall / "
      "IP allow-list (or your VPN) lets this machine connect.")),
    (re.compile(r"ssl error|ssl handshake|handshake failure|certificate verify"
                r"|server does not support ssl|ssl syscall|ssl connection has been closed"),
     ("SSL/TLS handshake with {target} failed — the server may require "
      "(or not support) an encrypted connection.")),
    (re.compile(r"port must be a number"),
     "Port must be a number (e.g. 5432)."),
]

_BACKGROUND = re.compile(r"\s*\(Background on this error at:[^)]*\)\s*")


def redact(text: str, secret: str) -> str:
    """Remove the secret (raw and URL-encoded) and any URL userinfo from text."""
    if secret:
        for form in {secret, quote_plus(secret), quote_plus(secret, safe="")}:
            text = text.replace(form, "***")
    # scheme://user:anything@host → scheme://user:***@host
    return re.sub(r"(\w[\w+.-]*://[^:/@\s]+):[^@\s]*@", r"\1:***@", text)


def friendly_db_error(exc: BaseException | str, *, host: str = "",
                      port: str | int | None = "", database: str = "",
                      secret: str = "") -> str:
    """Map a connection failure to an actionable, password-free message.

    Falls back to the (redacted, trimmed) raw error when no rule matches so
    nothing is hidden from the user.
    """
    raw = redact(str(exc), secret)
    low = raw.lower()
    target = f"{host}:{port}" if host and port else (host or "the server")
    for pattern, template in _RULES:
        if pattern.search(low):
            return template.format(host=host or "?", database=database or "?",
                                   target=target)
    cleaned = _BACKGROUND.sub(" ", raw)
    cleaned = re.sub(r"^\([\w.]+\)\s*", "", cleaned).strip()
    return f"Connection failed: {cleaned}"


def friendly_for_config(exc: BaseException, config: dict, secret: str) -> str:
    """``friendly_db_error`` fed from a datasource's stored config."""
    return friendly_db_error(exc, host=str(config.get("host", "")),
                             port=config.get("port") or "",
                             database=str(config.get("database", "")),
                             secret=secret)
