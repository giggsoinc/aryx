"""Ontology on/off A/B — the Accuracy Lab's fair comparison.

Same model, same question. Variant ON answers grounded in the resolved,
linked knowledge graph; variant OFF answers with no workspace grounding (the
vanilla-LLM baseline). The scorecard contrasts them on the only axis that
matters to a skeptic: is the answer backed by source records, or asserted?

Pure by design — the two answer strings are injected by the caller, so the
engine is testable without an LLM and the scoring can never itself drift.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from aryx.ask.evidence import RetrievedEntity
from aryx.ask.grounding import Grounding, build_grounding


@dataclass
class Variant:
    """One side of the A/B: the answer and its verified grounding."""

    label: str
    grounded_in_ontology: bool
    answer: str
    grounding: Grounding


@dataclass
class AbResult:
    """The full comparison, ready for the Lab scorecard."""

    question: str
    model: str
    on: Variant
    off: Variant
    scorecard: dict

    def to_dict(self) -> dict:
        """JSON-serializable form for the Lab UI."""
        return {
            "question": self.question,
            "model": self.model,
            "on": {**asdict(self.on), "grounding": self.on.grounding.to_dict()},
            "off": {**asdict(self.off), "grounding": self.off.grounding.to_dict()},
            "scorecard": self.scorecard,
        }


def _scorecard(on: Grounding, off: Grounding) -> dict:
    """Side-by-side metrics that expose grounded vs asserted."""
    return {
        "grounded": {"on": on.grounded, "off": off.grounded},
        "citations": {"on": len(on.citations), "off": len(off.citations)},
        "source_records": {"on": on.source_count, "off": off.source_count},
        "evidence_used": {"on": on.cited_count, "off": off.cited_count},
    }


def run_ab(question: str, evidence_on: list[RetrievedEntity],
           answer_on: str, answer_off: str, model: str = "") -> AbResult:
    """Build the A/B result from the two answers and the ON-side evidence.

    The OFF variant is graded against *no* evidence on purpose — that is what
    "ontology off" means — so it is grounded only if it cites nothing, which it
    cannot. The contrast is the whole point.
    """
    g_on = build_grounding(answer_on, evidence_on)
    g_off = build_grounding(answer_off, [])
    return AbResult(
        question=question,
        model=model,
        on=Variant("Ontology on", True, answer_on, g_on),
        off=Variant("Ontology off", False, answer_off, g_off),
        scorecard=_scorecard(g_on, g_off),
    )
