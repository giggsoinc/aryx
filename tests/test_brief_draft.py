from __future__ import annotations

from aryx.brief_draft import draft_from_text
from aryx.broker import Broker, Registry, TokenGovernor


def test_draft_from_text_falls_back_when_no_model_available() -> None:
    broker = Broker(Registry(), TokenGovernor({}))
    seed = (
        "Map each contract and its line items. A Contract is identified by its "
        "contract_number. Each contract has many contract lines, and every line "
        "is uniquely identified by its contract_number together with its "
        "line_number. Show how each contract connects to all of its line items."
    )

    brief = draft_from_text(broker, seed)

    assert brief["domain"]
    assert "Contract" in brief["scope"]
    assert "contract_number" in " ".join(brief["objectives"])
    assert "line_number" in " ".join(brief["objectives"])
