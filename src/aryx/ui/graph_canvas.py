"""Node/edge builders and visual constants for the graph canvas."""
from __future__ import annotations

from typing import Any

from streamlit_agraph import Config, Edge, Node

TYPE_COLORS: dict[str, str] = {
    "Customer": "#4A90E2",
    "SupportTicket": "#E8775A",
    "Organization": "#50C878",
    "Person": "#9B59B6",
    "Contract": "#F1C40F",
    "Vendor": "#1ABC9C",
}
DEFAULT_COLOR = "#95A5A6"
PATH_COLOR = "#F7C948"
PATH_EDGE_COLOR = "#F7C948"
NODE_FONT = {"size": 18, "color": "#FFFFFF", "face": "Inter, sans-serif",
             "strokeWidth": 4, "strokeColor": "#0e1117"}
EDGE_FONT = {"size": 14, "color": "#C8D0DC",
             "strokeWidth": 4, "strokeColor": "#0e1117"}


def _degree(entities: list[dict], rels: list[dict]) -> dict[int, int]:
    """Count incident edges per entity id so connected nodes render larger."""
    counts: dict[int, int] = {e["id"]: 0 for e in entities}
    for r in rels:
        counts[r["source"]] = counts.get(r["source"], 0) + 1
        counts[r["target"]] = counts.get(r["target"], 0) + 1
    return counts


def build_nodes(entities: list[dict], visible: set[int],
                degree: dict[int, int], highlight: set[int]) -> list[Node]:
    """Materialise visible entities into streamlit-agraph Nodes."""
    nodes: list[Node] = []
    for e in entities:
        if e["id"] not in visible:
            continue
        base = TYPE_COLORS.get(e["type"], DEFAULT_COLOR)
        color = PATH_COLOR if e["id"] in highlight else base
        size = 22 + min(degree.get(e["id"], 0), 8) * 4
        nodes.append(Node(
            id=str(e["id"]), label=e["name"] or f"#{e['id']}", size=size,
            color=color, title=f"{e['type']}: {e['name']}", font=NODE_FONT,
        ))
    return nodes


def build_edges(rels: list[dict], visible: set[int],
                highlight_pairs: set[tuple[int, int]]) -> list[Edge]:
    """Materialise relationships into Edges, colouring path-pairs distinctly."""
    edges: list[Edge] = []
    for r in rels:
        s, t = r["source"], r["target"]
        if s not in visible or t not in visible:
            continue
        on_path = (s, t) in highlight_pairs or (t, s) in highlight_pairs
        edges.append(Edge(
            source=str(s), target=str(t), label=r["name"], font=EDGE_FONT,
            color=PATH_EDGE_COLOR if on_path else "#5a6678",
            width=3 if on_path else 2,
        ))
    return edges


def canvas_config() -> Config:
    """Physics + spacing tuned for ~50 nodes on a 1200x700 canvas."""
    return Config(
        width=1200, height=700,
        directed=True, physics=True, hierarchical=False,
        nodeHighlightBehavior=True, highlightColor="#F7A7A6",
        nodeSpacing=280, linkLength=260,
    )


def legend_html(types: list[str]) -> str:
    """Inline-chip legend for the currently visible ontology types."""
    return "".join(
        f'<span style="display:inline-flex;align-items:center;'
        f'margin:0 14px 6px 0;">'
        f'<span style="width:14px;height:14px;border-radius:50%;background:'
        f'{TYPE_COLORS.get(t, DEFAULT_COLOR)};display:inline-block;'
        f'margin-right:6px;"></span>'
        f'<span style="font-size:0.95rem;color:#c8d0dc">{t}</span></span>'
        for t in types
    )


def derive_degree(entities: list[dict], rels: list[dict]) -> dict[int, int]:
    """Public wrapper so the panel can size nodes by connectivity."""
    return _degree(entities, rels)
