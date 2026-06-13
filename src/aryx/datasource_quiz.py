"""Datasource quiz definitions — kind-specific question packs (Slice 2).

Each kind returns a list of fields the agent must ask the user. Fields
flagged ``secret=true`` are stored encrypted and never echoed back.
Drives MCP ``datasource_quiz`` and the REST ``GET /admin/datasources/quiz``.
"""
from __future__ import annotations

_PG = [
    {"name": "host", "secret": False, "required": True,
     "help": "Postgres host (e.g. db.example.com)."},
    {"name": "port", "secret": False, "required": False,
     "help": "Default 5432."},
    {"name": "database", "secret": False, "required": True,
     "help": "Database name."},
    {"name": "user", "secret": False, "required": True,
     "help": "Database username."},
    {"name": "password", "secret": True, "required": True,
     "help": "Encrypted at rest with Fernet; never echoed."},
    {"name": "extra_context", "secret": False, "required": False,
     "help": "Optional notes — e.g. 'focus on Q3 onboarding tables'."},
]

_MYSQL = [
    {"name": "host", "secret": False, "required": True,
     "help": "MySQL/MariaDB host."},
    {"name": "port", "secret": False, "required": False,
     "help": "Default 3306."},
    {"name": "database", "secret": False, "required": True,
     "help": "Database/schema name."},
    {"name": "user", "secret": False, "required": True,
     "help": "Database user."},
    {"name": "password", "secret": True, "required": True,
     "help": "Encrypted at rest with Fernet; never echoed."},
    {"name": "extra_context", "secret": False, "required": False,
     "help": "Optional notes."},
]

_ORACLE = [
    {"name": "host", "secret": False, "required": True,
     "help": "Oracle host."},
    {"name": "port", "secret": False, "required": False,
     "help": "Default 1521."},
    {"name": "database", "secret": False, "required": True,
     "help": "Service name (e.g. ORCL)."},
    {"name": "user", "secret": False, "required": True,
     "help": "Database user."},
    {"name": "password", "secret": True, "required": True,
     "help": "Encrypted at rest with Fernet; never echoed."},
    {"name": "extra_context", "secret": False, "required": False,
     "help": "Optional notes."},
]

_DOCS = [
    {"name": "path", "secret": False, "required": True,
     "help": "Folder path containing PDF/DOCX/PPTX/CSV/JSON files."},
    {"name": "extra_context", "secret": False, "required": False,
     "help": "What the documents describe — drives entity extraction."},
]

_REST = [
    {"name": "url", "secret": False, "required": True,
     "help": "Base URL of the REST endpoint."},
    {"name": "auth_header", "secret": False, "required": False,
     "help": "Header name to attach (e.g. Authorization)."},
    {"name": "token", "secret": True, "required": False,
     "help": "Bearer token / API key; Fernet-encrypted."},
    {"name": "extra_context", "secret": False, "required": False,
     "help": "Optional notes about the API."},
]


_QUIZ = {"postgresql": _PG, "postgres": _PG, "mysql": _MYSQL,
         "mariadb": _MYSQL, "oracle": _ORACLE, "docs": _DOCS, "rest": _REST}


def quiz_for(kind: str) -> dict:
    """Return the quiz field list for a kind, or an error dict."""
    fields = _QUIZ.get(kind)
    if not fields:
        return {"error": f"unknown kind: {kind}",
                "supported": sorted(_QUIZ.keys())}
    return {"kind": kind, "fields": fields}


def supported_kinds() -> list[str]:
    """Return every datasource kind the quiz knows about."""
    return sorted(_QUIZ.keys())
