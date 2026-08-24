"""is_identifier_like / best_match_columns.

Regression coverage for two real bugs found this session:
- Employee records whose employee_id ("EMP101".."EMP108") sat first in the
  match text and collided on a shared blocking prefix.
- SupportTicket whose only match key was ticket_id ("TK101".."TK104"), so
  the whole match text — and the resulting "similarity" score — was just
  the ticket id.

And the regression THAT fix itself introduced, now fixed properly:
- Order's only match key was order_id. A first attempt replaced it with a
  single best free-text column (company_name alone) — which broke Order
  records, since two genuinely different orders can share a company. The
  fallback must pick SEVERAL non-identifier columns, not one.
"""
from __future__ import annotations

from aryx.resolution.field_shape import (
    best_match_columns,
    is_identifier_like,
    is_row_identifier,
    resolve_match_keys,
)

_EMPLOYEE_IDS = ["EMP101", "EMP102", "EMP103", "EMP104", "EMP105", "EMP106",
                "EMP107", "EMP108"]
_TICKET_IDS = ["TK101", "TK102", "TK103", "TK104"]
_COMPANY_IDS = ["CO101", "CO102"]
_NAMES = ["Jennifer Park", "Carlos Mendez", "Aisha Bello", "Daniel Wu"]
_EMAILS = ["jennifer.park@company.com", "carlos.mendez@company.com"]
_DEPARTMENTS = ["Sales", "Sales Dept", "Marketing", "Engineering"]


def test_sequential_employee_ids_are_identifier_like() -> None:
    assert is_identifier_like(_EMPLOYEE_IDS) is True


def test_ticket_ids_are_identifier_like() -> None:
    assert is_identifier_like(_TICKET_IDS) is True


def test_two_company_ids_are_identifier_like() -> None:
    """Real demo data was this small — must not require a big sample."""
    assert is_identifier_like(_COMPANY_IDS) is True


def test_person_names_are_not_identifier_like() -> None:
    assert is_identifier_like(_NAMES) is False


def test_emails_are_not_identifier_like() -> None:
    assert is_identifier_like(_EMAILS) is False


def test_department_names_are_not_identifier_like() -> None:
    assert is_identifier_like(_DEPARTMENTS) is False


def test_too_few_samples_is_not_flagged() -> None:
    """One value alone (however code-shaped) isn't enough to judge."""
    assert is_identifier_like(["EMP101"]) is False


def test_low_uniqueness_is_not_identifier_like() -> None:
    """Repeated values (a status/category column) fail the id shape even
    if a few of them happen to look code-like."""
    assert is_identifier_like(["Open", "Open", "Open", "Closed"]) is False


def test_ticket_fallback_prefers_subject_over_ticket_id() -> None:
    """The exact SupportTicket bug: ticket_id is MORE unique than subject
    could ever tie-break to, but subject is what should win."""
    colvals = {
        "ticket_id": _TICKET_IDS,
        "subject": ["Azure login failure", "Teams audio not working",
                   "Prime video buffering", "AWS billing discrepancy"],
        "company_ref": ["Microsoft", "Microsoft", "Amazon", "Amazon"],
    }
    result = best_match_columns(colvals, ["ticket_id", "subject", "company_ref"])
    assert "ticket_id" not in result
    assert "subject" in result


def test_order_fallback_keeps_several_columns_not_just_one() -> None:
    """The exact regression: company_name ALONE turned "same order?" into
    "same company?". Must keep other distinguishing columns too."""
    colvals = {
        "order_id": ["O101", "O102", "O103", "O104"],
        "company_name": ["Asha L.", "Byte Cafe", "Asha Labs", "Coda Shop"],
        "order_status": ["Open", "Shipped", "Open", "Delivered"],
        "product_name": ["Starter Kit", "Receipt Printer", "Receipt Printer",
                        "Barcode Scanner"],
    }
    result = best_match_columns(
        colvals, ["order_id", "company_name", "order_status", "product_name"])
    assert "order_id" not in result
    assert len(result) > 1, "must not collapse to a single column"
    assert "product_name" in result, "the column that actually separates O101/O103"


def test_fallback_caps_column_count() -> None:
    """Don't concatenate every free-text column in a wide table — cap it."""
    colvals = {f"col{i}": [f"value-{i}-{n}" for n in range(4)] for i in range(6)}
    result = best_match_columns(colvals, list(colvals), cap=3)
    assert len(result) == 3


def test_fallback_falls_back_to_uniqueness_among_ids() -> None:
    """If every candidate is identifier-shaped, still pick one rather than
    refusing to pick anything."""
    colvals = {"a_id": ["A101", "A102"], "b_id": ["B201", "B202", "B203"]}
    assert best_match_columns(colvals, ["a_id", "b_id"]) == ["b_id"]


def test_order_id_is_a_row_identifier() -> None:
    """The exact transactional-type signal: 7 distinct order_ids."""
    assert is_row_identifier(["O101", "O102", "O103", "O104", "O105", "O106", "O107"]) is True


def test_ticket_id_is_a_row_identifier() -> None:
    assert is_row_identifier(_TICKET_IDS) is True


def test_employee_id_with_one_repeat_is_not_a_row_identifier() -> None:
    """The narrow guard: is_identifier_like tolerates a 90% uniqueness
    ratio, but is_row_identifier requires every value distinct — a single
    accidental repeat (e.g. a re-onboarded employee reusing an old id)
    must not trigger the resolution bypass for what's really a dimension
    type."""
    values = [f"EMP{100 + i}" for i in range(20)] + ["EMP100"]  # 21 rows, 1 repeat
    assert is_identifier_like(values) is True
    assert is_row_identifier(values) is False


def test_person_names_are_not_row_identifiers() -> None:
    """Free text, however unique in this sample, is never a row identifier —
    the code-shape requirement is what protects Company/Employee from
    being misclassified as transactional."""
    assert is_row_identifier(_NAMES) is False


def test_too_few_samples_is_not_a_row_identifier() -> None:
    assert is_row_identifier(["O101"]) is False


def test_resolve_match_keys_triggers_bypass_for_a_lone_order_id() -> None:
    """The actual ingest decision, not just its building blocks: exactly
    one proposed key, and it's a real per-row identifier -> bypass."""
    colvals = {
        "order_id": ["O101", "O102", "O103", "O104"],
        "company_name": ["Asha L.", "Byte Cafe", "Asha Labs", "Coda Shop"],
    }
    keys, transactional = resolve_match_keys(["order_id"], colvals)
    assert transactional is True
    assert keys == ["order_id"]


def test_resolve_match_keys_no_bypass_for_multi_key_proposal() -> None:
    """More than one proposed key -> never transactional, even if one of
    them is identifier-shaped (the Employee case: drop the id, keep the
    rest, proceed through normal resolution)."""
    colvals = {
        "employee_id": ["EMP101", "EMP102", "EMP103"],
        "employee_name": ["Riya Shah", "Noah Kim", "Alex Turner"],
    }
    keys, transactional = resolve_match_keys(["employee_id", "employee_name"], colvals)
    assert transactional is False
    assert keys == ["employee_name"]


def test_resolve_match_keys_no_bypass_when_lone_key_is_free_text() -> None:
    """A single proposed key that ISN'T a row identifier (e.g. a name
    column) must never trigger the bypass — only exercises the
    free-text-survives-repair path."""
    colvals = {"name": ["Asha Corp", "Byte Cafe", "Coda Shop"]}
    keys, transactional = resolve_match_keys(["name"], colvals)
    assert transactional is False
    assert keys == ["name"]


def test_resolve_match_keys_falls_back_to_best_columns_when_lone_key_invalid() -> None:
    """A single proposed key that isn't even a real column falls through to
    the whole-file fallback, same as before this function existed —
    the ticket_id-only regression, minus the id-shaped decoy."""
    colvals = {
        "ticket_id": ["TK101", "TK102", "TK103"],
        "subject": ["Azure login failure", "Teams audio not working",
                   "Prime video buffering"],
    }
    keys, transactional = resolve_match_keys(["bogus_key"], colvals)
    assert transactional is False
    assert "ticket_id" not in keys
    assert "subject" in keys


def test_resolve_match_keys_returns_proposal_unchanged_with_no_columns() -> None:
    """Degenerate case: the file has no columns at all — nothing to repair
    with, so the original proposal passes through untouched."""
    keys, transactional = resolve_match_keys(["name"], {})
    assert transactional is False
    assert keys == ["name"]
