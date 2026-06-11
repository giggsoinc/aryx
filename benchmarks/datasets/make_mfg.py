"""Synthetic supplier-company ER dataset with controlled corruption.

Mirrors the Aryx sales demo domain: manufacturing/supplier records with
abbreviations (Corp/Corporation), legal suffixes (LLC/L.L.C.), word-order
permutations, edit-distance 1-2 typos, and 30% exact duplicates.
"""
from __future__ import annotations

import itertools
import random

_ADJECTIVES = [
    "Allied", "American", "Applied", "Apex", "Advanced", "Atlas", "Beacon",
    "Blue", "Central", "Continental", "Delta", "Dynamic", "Eastern", "Elite",
    "Empire", "Falcon", "Federal", "First", "General", "Global", "Golden",
    "Grand", "Great", "Green", "Heritage", "Horizon", "Imperial", "Integral",
    "Interstate", "Iron", "Key", "Liberty", "Lincoln", "Lone", "Metro",
    "Midwest", "Modern", "National", "New", "Northern", "Pacific", "Peak",
    "Pioneer", "Premier", "Prime", "Pro", "Quality", "Rapid", "Reliable",
    "Royal", "Southern", "Standard", "Superior", "Swift", "Tri", "Unified",
    "United", "Universal", "Valley", "Victory", "Western", "Zenith",
]
_INDUSTRIES = [
    "Aerospace", "Alloy", "Assembly", "Auto", "Chemical", "Component",
    "Engineering", "Fabrication", "Fluid", "Forge", "Gear", "Industrial",
    "Instrument", "Laser", "Logistics", "Machine", "Material", "Metal",
    "Micro", "Mold", "Motor", "Optical", "Parts", "Pipe", "Plastics",
    "Polymer", "Power", "Precision", "Process", "Production", "Pump",
    "Rubber", "Sensor", "Sheet", "Signal", "Steel", "Systems", "Thermal",
    "Tooling", "Valve", "Wire",
]
_SUFFIX_VARIANTS: list[list[str]] = [
    ["Corp", "Corporation"],
    ["Inc", "Inc.", "Incorporated"],
    ["LLC", "L.L.C.", "Limited Liability Company"],
    ["Ltd", "Ltd.", "Limited"],
    ["Co", "Co.", "Company"],
    ["Mfg", "Mfg.", "Manufacturing"],
    ["Intl", "Intl.", "International"],
]
_SUFFIX_CANONICAL = [variants[0] for variants in _SUFFIX_VARIANTS]


def _gen_base_names(n: int, rng: random.Random) -> list[str]:
    """Generate n unique base company names like 'Apex Industrial Corp'."""
    seen: set[str] = set()
    names: list[str] = []
    pool = list(itertools.product(_ADJECTIVES, _INDUSTRIES, _SUFFIX_CANONICAL))
    rng.shuffle(pool)
    for adj, ind, suf in pool:
        name = f"{adj} {ind} {suf}"
        if name not in seen:
            seen.add(name)
            names.append(name)
        if len(names) >= n:
            break
    while len(names) < n:
        names.append(f"Firm{len(names)}")
    return names


def _typo(text: str, rng: random.Random) -> str:
    """Introduce one edit-distance-1 corruption."""
    if len(text) < 3:
        return text
    op = rng.choice(["swap", "sub", "del", "ins"])
    i = rng.randint(1, len(text) - 2)
    chars = list(text)
    if op == "swap" and i < len(text) - 1:
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
        return "".join(chars)
    if op == "sub":
        repl = rng.choice([c for c in "abcdefghijklmnopqrstuvwxyz"
                           if c != chars[i].lower()])
        chars[i] = repl if chars[i].islower() else repl.upper()
        return "".join(chars)
    if op == "del":
        return text[:i] + text[i + 1:]
    return text[:i] + rng.choice("abcdefghijklmnopqrstuvwxyz") + text[i:]


def _word_order(name: str, rng: random.Random) -> str:
    """Permute the words in a name."""
    words = name.split()
    if len(words) < 3:
        return name
    rng.shuffle(words)
    return " ".join(words)


def _suffix_variant(name: str, rng: random.Random) -> str:
    """Replace the canonical suffix with an alternate form."""
    for variants in _SUFFIX_VARIANTS:
        if variants[0] in name:
            return name.replace(variants[0], rng.choice(variants[1:]), 1)
    return name


def _corrupt(name: str, rng: random.Random) -> str:
    """Apply one or two random corruptions to a name."""
    ops = rng.sample(["suffix", "word_order", "typo", "typo2"],
                     k=rng.randint(1, 2))
    result = name
    for op in ops:
        if op == "suffix":
            result = _suffix_variant(result, rng)
        elif op == "word_order":
            result = _word_order(result, rng)
        else:
            result = _typo(result, rng)
    return result


def load_mfg(n_originals: int = 5000,
             seed: int = 42) -> tuple[dict[str, dict], set[frozenset]]:
    """Generate supplier records: each original gets one duplicate.

    30% of originals get an exact duplicate; the rest get a corrupted copy.
    Total records = 2 * n_originals.

    Returns:
        (records_dict, true_pairs_set) where records_dict maps
        "mfg-{i}-orig|dup" to {"name", "category"} and true_pairs_set holds
        frozenset id pairs.
    """
    rng = random.Random(seed)
    base_names = _gen_base_names(n_originals, rng)
    records: dict[str, dict] = {}
    true_pairs: set[frozenset] = set()
    categories = ["Tier1", "Tier2", "Tier3", "OEM", "Distributor"]

    for i, name in enumerate(base_names):
        orig_id, dup_id = f"mfg-{i}-orig", f"mfg-{i}-dup"
        cat = rng.choice(categories)
        records[orig_id] = {"name": name, "category": cat}
        dup_name = name if rng.random() < 0.30 else _corrupt(name, rng)
        records[dup_id] = {"name": dup_name, "category": cat}
        true_pairs.add(frozenset([orig_id, dup_id]))

    return records, true_pairs
