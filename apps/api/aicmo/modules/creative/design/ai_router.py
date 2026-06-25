"""AI Edit Router — natural language → validated EditOps (CS4, Guided real).

A single LLM call turns an instruction + the current design's layer inventory
into a structured plan: an op-class (edit / regenerate / transform / restyle /
variant), a confidence score, a human summary, and — for in-place edits — a
list of EditOps that target REAL layer ids. The ops are converted to the
canonical grammar and validated through `parse_ops`; anything the LLM gets
wrong (missing layer, bad op) is dropped and lowers confidence.

When the LLM is unavailable, a deterministic rule-based planner takes over so
NL editing still works (at lower confidence). Nothing here mutates a design —
the caller routes the plan through `apply_revision` (Law 3).
"""

from __future__ import annotations

from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.creative.design.ops import OpError, parse_ops

log = structlog.get_logger()

OpClass = Literal["edit", "regenerate", "transform", "restyle", "variant"]

_RESTYLE_WORDS = ("luxury", "modern", "playful", "premium", "minimal", "bold",
                  "elegant", "style", "vibe", "mood", "look", "feel")
_TRANSFORM_WORDS = ("instagram", "linkedin", "story", "carousel", "reel",
                    "format", "convert", "resize", "tiktok", "shorts", "poster", "turn this")
_REGEN_WORDS = ("regenerate", "redo", "another version", "try again", "new version", "start over")
_VARIANT_WORDS = ("variant", "variants", "versions", "options", "alternatives")


# ---------------------------------------------------------------------
#  LLM I/O — a flat, easy-to-emit op shape; the server enforces the real
#  grammar. (Discriminated unions are hard for models; flat is reliable.)
# ---------------------------------------------------------------------
class LlmOp(BaseModel):
    op: Literal[
        "set_text", "move_layer", "resize_layer", "apply_brand_token",
        "set_background_color", "update_text_style",
    ]
    layer_id: str | None = None
    text: str | None = None
    field: str | None = None
    token: str | None = None
    color: str | None = None
    weight: Literal["regular", "medium", "semibold", "bold"] | None = None
    align: Literal["left", "center", "right", "justify"] | None = None
    font_size: float | None = None
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None


class LlmEditPlan(BaseModel):
    op_class: OpClass
    confidence: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1, max_length=240)
    ops: list[LlmOp] = Field(default_factory=list)
    style: str | None = None
    transform_kind: Literal["reformat", "recompose", "remediate"] | None = None
    target_aspect: Literal["1:1", "4:5", "9:16", "16:9"] | None = None
    variant_count: int | None = Field(default=None, ge=1, le=8)


class EditPlan(BaseModel):
    """The server-validated plan the dispatcher acts on."""

    op_class: OpClass
    confidence: int
    summary: str
    ops: list[dict[str, Any]] = Field(default_factory=list)  # canonical, validated
    style: str | None = None
    transform_kind: str | None = None
    target_aspect: str | None = None
    variant_count: int | None = None
    source: Literal["llm", "fallback"] = "fallback"
    notes: str | None = None


SYSTEM_PROMPT = (
    "You edit an existing layered design from a natural-language instruction. "
    "You are given the design's LAYERS (id, role, type, current text). Decide the "
    "op_class and return a plan:\n"
    "- edit: small change to existing layers → return `ops` targeting real layer ids.\n"
    "- regenerate: rewrite the copy of existing layers → `ops` (set_text).\n"
    "- restyle: change the visual style (luxury/modern/…) → set `style`.\n"
    "- transform: change format/platform/media (LinkedIn, Story, poster→carousel, "
    "carousel→reel) → set `transform_kind` (reformat|recompose|remediate) and "
    "`target_aspect`.\n"
    "- variant: make N alternative versions → set `variant_count`.\n"
    "Op types: set_text(layer_id,text), move_layer(layer_id,x,y), "
    "resize_layer(layer_id,w,h), apply_brand_token(layer_id,field,token e.g. "
    "field=color token=brand:primary), set_background_color(color), "
    "update_text_style(layer_id, weight/align/font_size/color). Coordinates are "
    "0..1 fractions. Only target layer ids that exist. Give an honest confidence "
    "(0-100). Industry is context for copy, never a template."
)


def classify(instruction: str) -> OpClass:
    """Rule-based classifier (the fallback + a fast pre-check)."""
    low = instruction.lower()
    if any(w in low for w in _VARIANT_WORDS):
        return "variant"
    if any(w in low for w in _REGEN_WORDS):
        return "regenerate"
    if any(w in low for w in _TRANSFORM_WORDS):
        return "transform"
    if any(w in low for w in _RESTYLE_WORDS):
        return "restyle"
    return "edit"


# ---------------------------------------------------------------------
#  Inventory + op conversion
# ---------------------------------------------------------------------
def _inventory(doc: dict[str, Any]) -> str:
    lines: list[str] = []
    for pi, page in enumerate(doc.get("pages", [])):
        for ly in page.get("layers", []):
            txt = ly.get("text")
            snip = f' text="{txt[:40]}"' if txt else ""
            lines.append(f"page{pi} id={ly.get('id')} role={ly.get('role')} type={ly.get('type')}{snip}")
    return "\n".join(lines) or "(empty design)"


def _all_layer_ids(doc: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for page in doc.get("pages", []):
        for ly in page.get("layers", []):
            if ly.get("id"):
                ids.add(ly["id"])
    return ids


def _to_canonical(o: LlmOp) -> dict[str, Any] | None:
    if o.op == "set_text" and o.layer_id and o.text is not None:
        return {"op": "set_text", "layer_id": o.layer_id, "text": o.text}
    if o.op == "move_layer" and o.layer_id and o.x is not None and o.y is not None:
        return {"op": "move_layer", "layer_id": o.layer_id, "x": o.x, "y": o.y}
    if o.op == "resize_layer" and o.layer_id and o.w is not None and o.h is not None:
        return {"op": "resize_layer", "layer_id": o.layer_id, "w": o.w, "h": o.h}
    if o.op == "apply_brand_token" and o.layer_id and o.field and o.token:
        return {"op": "apply_brand_token", "layer_id": o.layer_id, "field": o.field, "token": o.token}
    if o.op == "set_background_color" and o.color:
        return {"op": "set_background", "page_index": 0, "background": {"kind": "color", "color": o.color}}
    if o.op == "update_text_style" and o.layer_id:
        props = {k: v for k, v in (("color", o.color), ("weight", o.weight),
                                   ("align", o.align), ("font_size", o.font_size)) if v is not None}
        if props:
            return {"op": "update_layer", "layer_id": o.layer_id, "props": props}
    return None


def _validate_ops(raw: list[dict[str, Any]], doc: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """Keep only ops that parse AND target an existing layer. Returns
    (kept, dropped_count)."""
    ids = _all_layer_ids(doc)
    kept: list[dict[str, Any]] = []
    dropped = 0
    for d in raw:
        lid = d.get("layer_id")
        if lid is not None and lid not in ids:
            dropped += 1
            continue
        try:
            parse_ops([d])  # grammar validation
        except (OpError, Exception):  # noqa: BLE001
            dropped += 1
            continue
        kept.append(d)
    return kept, dropped


# ---------------------------------------------------------------------
#  The planner
# ---------------------------------------------------------------------
async def plan_edit(instruction: str, doc: dict[str, Any], *, allow_llm: bool = True) -> EditPlan:
    if allow_llm:
        try:
            return await _llm_plan(instruction, doc)
        except Exception as e:  # noqa: BLE001 — never block editing on an LLM error
            log.warning("creative.nl_edit.llm_fallback", error=str(e))
    return _fallback_plan(instruction, doc)


async def _llm_plan(instruction: str, doc: dict[str, Any]) -> EditPlan:
    user = (
        f"INSTRUCTION: {instruction}\n\nDESIGN LAYERS:\n{_inventory(doc)}\n\n"
        "Return the edit plan."
    )
    router = get_llm_router()
    result = await router.generate(
        response_schema=LlmEditPlan, system=SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=user)], temperature=0.3, max_tokens=1200,
    )
    plan = result.data
    ops, dropped = _validate_ops([c for o in plan.ops if (c := _to_canonical(o))], doc)
    confidence = plan.confidence
    notes = None
    if plan.op_class in ("edit", "regenerate"):
        if not ops:
            confidence = min(confidence, 20)
            notes = "No applicable changes were produced."
        elif dropped:
            confidence = max(0, confidence - 15 * dropped)
            notes = f"{dropped} suggested change(s) didn't fit and were dropped."
    return EditPlan(
        op_class=plan.op_class, confidence=confidence, summary=plan.summary, ops=ops,
        style=plan.style, transform_kind=plan.transform_kind, target_aspect=plan.target_aspect,
        variant_count=plan.variant_count, source="llm", notes=notes,
    )


def _first_text_layer_id(doc: dict[str, Any]) -> str | None:
    for page in doc.get("pages", []):
        for ly in page.get("layers", []):
            if ly.get("type") == "text":
                return ly.get("id")
    return None


_IMAGE_NOUNS = ("image", "photo", "picture", "background", "person", "headshot",
                "logo", "laptop", "product", "graphic", "visual", "bg")


def first_image_layer_id(doc: dict[str, Any], *, hint: str | None = None) -> str | None:
    """Pick the image layer to replace. If a hint word matches a role (e.g.
    'logo', 'product', 'background'), prefer that; else the first image layer."""
    images = [ly for page in doc.get("pages", []) for ly in page.get("layers", [])
              if ly.get("type") == "image"]
    if hint:
        low = hint.lower()
        for ly in images:
            role = (ly.get("role") or "").lower()
            if role and role in low:
                return ly.get("id")
    return images[0].get("id") if images else None


def is_image_replace(instruction: str) -> bool:
    low = instruction.lower()
    return ("replace" in low or "swap" in low or "change" in low) and (
        " with " in low or any(n in low for n in _IMAGE_NOUNS)
    )


def extract_replace_target(instruction: str) -> str:
    """The desired new image, e.g. 'replace this person with a female doctor'
    → 'a female doctor'; 'replace background with office' → 'office'."""
    low = instruction.lower()
    if " with " in low:
        idx = low.rindex(" with ")
        return instruction[idx + 6:].strip().rstrip(".") or instruction.strip()
    return instruction.strip()


def _cta_or_first_text(doc: dict[str, Any]) -> str | None:
    for page in doc.get("pages", []):
        for ly in page.get("layers", []):
            if ly.get("type") == "text" and ly.get("role") == "cta":
                return ly.get("id")
    return _first_text_layer_id(doc)


def stub_edit_ops(doc: dict[str, Any], instruction: str) -> list[dict[str, Any]]:
    """Deterministic op generator for a plain 'edit' (fallback). Sets the first
    text layer to the instruction, or adds a body layer if there's no text."""
    import uuid

    tid = _first_text_layer_id(doc)
    if tid is not None:
        return [{"op": "set_text", "layer_id": tid, "text": instruction[:200]}]
    return [{
        "op": "add_layer", "page_index": 0,
        "layer": {"type": "text", "id": f"body_{uuid.uuid4().hex[:8]}", "role": "body",
                  "text": instruction[:200], "x": 0.1, "y": 0.5, "w": 0.8, "h": 0.2,
                  "color": "brand:ink"},
    }]


def _fallback_plan(instruction: str, doc: dict[str, Any]) -> EditPlan:
    op_class = classify(instruction)
    low = instruction.lower()
    if op_class in ("edit", "regenerate"):
        # Heuristic: "stronger CTA" → embolden the CTA; else echo onto first text.
        if "cta" in low and ("strong" in low or "bold" in low or "punch" in low):
            cid = _cta_or_first_text(doc)
            ops = (
                [{"op": "update_layer", "layer_id": cid, "props": {"weight": "bold", "font_size": 0.05}}]
                if cid else []
            )
            summary = "Make the CTA bolder."
        elif "brand color" in low or "brand colours" in low or "use brand" in low:
            ids = list(_all_layer_ids(doc))[:1]
            ops = [{"op": "apply_brand_token", "layer_id": i, "field": "color", "token": "brand:primary"}
                   for i in ids]
            summary = "Apply brand colors."
        else:
            # echo onto the first existing text layer (skip add_layer — keep edits
            # constrained to existing layers in the fallback).
            tid = _first_text_layer_id(doc)
            ops = [{"op": "set_text", "layer_id": tid, "text": instruction[:200]}] if tid else []
            summary = "Apply your edit."
        kept, _ = _validate_ops(ops, doc)
        return EditPlan(op_class=op_class, confidence=55 if kept else 25,
                        summary=summary, ops=kept, source="fallback")
    if op_class == "restyle":
        return EditPlan(op_class="restyle", confidence=60, summary="Create a restyled version.",
                        style=instruction.strip()[:80], source="fallback")
    if op_class == "transform":
        # Target media wins: "carousel → reel" is a remediate (to video), not a recompose.
        if "reel" in low or "video" in low:
            kind = "remediate"
        elif "carousel" in low:
            kind = "recompose"
        else:
            kind = "reformat"
        aspect = ("9:16" if any(w in low for w in ("story", "reel", "tiktok", "shorts"))
                  else "1:1" if "linkedin" in low or "square" in low else None)
        return EditPlan(op_class="transform", confidence=55, summary="Transform to a new format.",
                        transform_kind=kind, target_aspect=aspect, source="fallback")
    # variant
    n = next((int(w) for w in low.split() if w.isdigit()), 3)
    return EditPlan(op_class="variant", confidence=60, summary=f"Create {min(n,8)} variants.",
                    variant_count=min(n, 8), source="fallback")
