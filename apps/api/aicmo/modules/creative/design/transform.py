"""Transform Engine — reformat / recompose / remediate + restyle.

A transform produces a NEW `creative_design` (transform = derive, never
mutate the source). CS1 ships deterministic STUB transforms that prove the
contract (new design + preserved source + metering + audit); CS3 swaps the
stub bodies for real composers. The signatures and the routes do not change.

A stub compose builds a minimal, on-brand layer doc from a brief — enough
for the AI-Mode path to produce revision 1 without an LLM.
"""

from __future__ import annotations

import copy
from typing import Any

from aicmo.modules.creative.design.layer_schema import LayerDoc


def stub_compose(
    *,
    format_slug: str | None,
    headline: str | None = None,
    subhead: str | None = None,
    cta: str | None = None,
) -> dict[str, Any]:
    """CS1 AI-Mode stub composer → a minimal on-brand LayerDoc. CS3 replaces
    this with the Strategy-driven composers (dynamic template engine)."""
    layers: list[dict[str, Any]] = []
    y = 0.12
    if headline:
        layers.append({"type": "text", "id": "headline", "role": "headline",
                       "text": headline[:200], "x": 0.08, "y": y, "w": 0.84, "h": 0.22,
                       "color": "brand:ink", "weight": "bold", "align": "left"})
        y += 0.26
    if subhead:
        layers.append({"type": "text", "id": "subhead", "role": "subhead",
                       "text": subhead[:300], "x": 0.08, "y": y, "w": 0.84, "h": 0.16,
                       "color": "brand:ink", "align": "left"})
        y += 0.20
    if cta:
        layers.append({"type": "text", "id": "cta", "role": "cta",
                       "text": cta[:80], "x": 0.08, "y": 0.82, "w": 0.5, "h": 0.1,
                       "color": "brand:primary", "weight": "semibold"})
    doc = LayerDoc(
        format_slug=format_slug,
        pages=[{"background": {"kind": "color", "color": "brand:surface"}, "layers": layers}],
    )
    return doc.model_dump(mode="json")


def stub_transform_doc(
    source_doc: dict[str, Any], kind: str, target_format_slug: str | None = None
) -> dict[str, Any]:
    """CS1 stub: clone the source doc, retarget the format for `reformat`.
    `recompose`/`remediate` are derive-only placeholders until CS3."""
    d = copy.deepcopy(source_doc)
    if kind == "reformat" and target_format_slug:
        d["format_slug"] = target_format_slug
    return d


def stub_restyle_doc(source_doc: dict[str, Any], style: str) -> dict[str, Any]:
    """CS1 stub: derive a new design preserving message + layout. CS3
    re-derives the visual system (color/type/imagery) from the style."""
    return copy.deepcopy(source_doc)
