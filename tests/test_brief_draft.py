from __future__ import annotations

from aryx.brief_draft import draft_from_text
from aryx.broker import Broker, Registry, TokenGovernor


def test_draft_from_text_falls_back_when_no_model_available() -> None:
    broker = Broker(Registry(), TokenGovernor({}))
    seed = (
        "Map each parent record and its child records. A ParentRecord is "
        "identified by its parent_key. Each parent has many child records, and "
        "every child is uniquely identified by its parent_key together with its "
        "child_key. Show how each parent connects to all of its children."
    )

    brief = draft_from_text(broker, seed)

    assert brief["domain"]
    assert brief["scope"]
    assert "parent_key" in " ".join(brief["objectives"])
    assert "child_key" in " ".join(brief["objectives"])
