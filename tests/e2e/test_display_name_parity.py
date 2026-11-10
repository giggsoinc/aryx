"""aryx_display_name (SQL) must equal the Python rule it replaces.

The Python reference below is a verbatim copy of the removed FalkorDB node-name rule,
falkor_store._display_name
(plus the "#<id>" fallback add_entity applied), kept here because that module
is deleted in this change. Attributes are round-tripped through jsonb first,
because production reads them from Postgres: the Python side sees keys in
jsonb's stored order, and the SQL function must pick the same "first" value.

Known, documented deviation (excluded from the generator): a NON-EMPTY list or
dict value would render as Python repr() there and as JSON text here.
"""
from __future__ import annotations

import random
from typing import Any

import psycopg
import pytest
from psycopg.types.json import Json

pytestmark = pytest.mark.e2e

_NAME_KEYS = ("name", "full_name", "title", "label", "ticket_ref", "ref",
              "sku", "code", "email", "username")
_VALUES: list[Any] = [
    "", "a", "Acme Corp", "x" * 80, "x" * 81, "  ", "Zoë Ünï 日本",
    "100% real_deal", 0, 1, -7, 123, 10 ** 20, 0.0, 1.5, 0.25, 100.0, -2.5,
    True, False, None, [], {},
]
_KEYS = list(_NAME_KEYS) + ["city", "note", "zeta", "alpha_key", "a", "zz",
                            "misc_field", "Name", "NAME"]


def display_name_ref(attrs: dict[str, Any], entity_id: int) -> str:
    """Verbatim copy of the removed falkor_store._display_name + the '#<id>' fallback."""
    for key in _NAME_KEYS:
        value = attrs.get(key)
        if value:
            return str(value)
    for value in attrs.values():
        if isinstance(value, str) and 0 < len(value) <= 80:
            return value
    return f"#{entity_id}"


def _cases(n: int, seed: int = 7) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    out: list[dict[str, Any]] = [{}]
    for _ in range(n):
        k = rng.randint(1, 5)
        out.append({rng.choice(_KEYS): rng.choice(_VALUES) for _ in range(k)})
    return out


def test_display_name_matches_python_reference(e2e_dsn: str) -> None:
    """About 600 generated attribute sets: SQL equals the Python rule."""
    mismatches = []
    with psycopg.connect(e2e_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            for i, attrs in enumerate(_cases(600)):
                cur.execute("SELECT %s::jsonb, aryx_display_name(%s::jsonb, %s)",
                            (Json(attrs), Json(attrs), 1000 + i))
                stored, sql_name = cur.fetchone()
                expected = display_name_ref(stored, 1000 + i)
                if sql_name != expected:
                    mismatches.append((attrs, expected, sql_name))
    assert not mismatches, f"{len(mismatches)} mismatches, first: {mismatches[:3]}"


def test_key_order_follows_stored_jsonb_order(e2e_dsn: str) -> None:
    """Shorter keys sort first in jsonb, so 'zeta' beats 'alpha_key'."""
    attrs = {"zeta": "z-val", "alpha_key": "a-val"}
    with psycopg.connect(e2e_dsn, autocommit=True) as conn:
        row = conn.execute("SELECT aryx_display_name(%s::jsonb, 1)",
                           (Json(attrs),)).fetchone()
    assert row[0] == "z-val"


def test_boolean_true_renders_python_style(e2e_dsn: str) -> None:
    """str(True) is 'True', not JSON's 'true'."""
    with psycopg.connect(e2e_dsn, autocommit=True) as conn:
        row = conn.execute("SELECT aryx_display_name(%s::jsonb, 5)",
                           (Json({"name": True}),)).fetchone()
    assert row[0] == "True"
