"""EditOp grammar + the pure `apply_ops` transform.

Both the AI (Guided Mode) and the future canvas editor (Pro Mode) emit the
SAME ops (Law 3). `apply_ops(doc, ops)` is a pure function: it deep-copies
the doc dict, applies each op, and returns the new dict — it does NOT
validate (the revision engine validates the result against the closed
layer schema). Keeping it pure makes it trivially testable and identical
for human and AI callers.
"""

from __future__ import annotations

import copy
import uuid
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class _Op(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddLayer(_Op):
    op: Literal["add_layer"] = "add_layer"
    page_index: int = Field(default=0, ge=0)
    layer: dict[str, Any]


class UpdateLayer(_Op):
    op: Literal["update_layer"] = "update_layer"
    layer_id: str
    props: dict[str, Any]


class MoveLayer(_Op):
    op: Literal["move_layer"] = "move_layer"
    layer_id: str
    x: float
    y: float


class ResizeLayer(_Op):
    op: Literal["resize_layer"] = "resize_layer"
    layer_id: str
    w: float
    h: float


class DeleteLayer(_Op):
    op: Literal["delete_layer"] = "delete_layer"
    layer_id: str


class Reorder(_Op):
    op: Literal["reorder"] = "reorder"
    page_index: int = Field(default=0, ge=0)
    layer_ids: list[str]


class SetText(_Op):
    op: Literal["set_text"] = "set_text"
    layer_id: str
    text: str


class ReplaceImage(_Op):
    """Point an image layer at a different (tenant-owned) asset — used by
    image replace, AI replace, and background removal (new transparent asset).
    The previous asset is untouched; only the layer's pointer changes."""

    op: Literal["replace_image"] = "replace_image"
    layer_id: str
    asset_id: uuid.UUID


class ApplyBrandToken(_Op):
    op: Literal["apply_brand_token"] = "apply_brand_token"
    layer_id: str
    field: str
    token: str  # e.g. "brand:primary"


class SetAnimation(_Op):
    op: Literal["set_animation"] = "set_animation"
    layer_id: str
    animation: dict[str, Any]


class SetBackground(_Op):
    op: Literal["set_background"] = "set_background"
    page_index: int = Field(default=0, ge=0)
    background: dict[str, Any]


class AddPage(_Op):
    op: Literal["add_page"] = "add_page"
    page: dict[str, Any] | None = None
    at_index: int | None = None


class DeletePage(_Op):
    op: Literal["delete_page"] = "delete_page"
    page_index: int = Field(ge=0)


EditOp = Annotated[
    Union[
        AddLayer, UpdateLayer, MoveLayer, ResizeLayer, DeleteLayer, Reorder,
        SetText, ReplaceImage, ApplyBrandToken, SetAnimation, SetBackground,
        AddPage, DeletePage,
    ],
    Field(discriminator="op"),
]


class _OpEnvelope(BaseModel):
    op: EditOp


def parse_ops(raw_ops: list[dict[str, Any]]) -> list[EditOp]:
    """Validate a list of op dicts into typed EditOps (discriminated)."""
    return [_OpEnvelope(op=o).op for o in raw_ops]


class OpError(ValueError):
    """An op referenced a missing layer/page or was otherwise unapplicable."""


def _find_layer(layers: list[dict], layer_id: str) -> dict | None:
    for ly in layers:
        if ly.get("id") == layer_id:
            return ly
        if ly.get("type") == "group":
            found = _find_layer(ly.get("children", []), layer_id)
            if found is not None:
                return found
    return None


def _remove_layer(layers: list[dict], layer_id: str) -> bool:
    for i, ly in enumerate(layers):
        if ly.get("id") == layer_id:
            layers.pop(i)
            return True
        if ly.get("type") == "group" and _remove_layer(ly.get("children", []), layer_id):
            return True
    return False


def _page(doc: dict, idx: int) -> dict:
    pages = doc.get("pages", [])
    if idx < 0 or idx >= len(pages):
        raise OpError(f"page_index {idx} out of range (0..{len(pages) - 1})")
    return pages[idx]


def _require_layer(doc: dict, layer_id: str) -> dict:
    for page in doc.get("pages", []):
        ly = _find_layer(page.get("layers", []), layer_id)
        if ly is not None:
            return ly
    raise OpError(f"layer {layer_id!r} not found")


def apply_ops(doc: dict[str, Any], ops: list[EditOp]) -> dict[str, Any]:
    """Pure: returns a NEW doc dict with the ops applied. Does not validate
    the result (the revision engine does). Raises OpError if an op targets a
    missing layer/page."""
    d = copy.deepcopy(doc)
    d.setdefault("pages", [])
    for op in ops:
        if isinstance(op, AddLayer):
            _page(d, op.page_index).setdefault("layers", []).append(copy.deepcopy(op.layer))
        elif isinstance(op, UpdateLayer):
            _require_layer(d, op.layer_id).update(copy.deepcopy(op.props))
        elif isinstance(op, MoveLayer):
            ly = _require_layer(d, op.layer_id)
            ly["x"], ly["y"] = op.x, op.y
        elif isinstance(op, ResizeLayer):
            ly = _require_layer(d, op.layer_id)
            ly["w"], ly["h"] = op.w, op.h
        elif isinstance(op, DeleteLayer):
            if not any(_remove_layer(p.get("layers", []), op.layer_id) for p in d["pages"]):
                raise OpError(f"layer {op.layer_id!r} not found")
        elif isinstance(op, Reorder):
            page = _page(d, op.page_index)
            by_id = {ly.get("id"): ly for ly in page.get("layers", [])}
            if set(op.layer_ids) != set(by_id):
                raise OpError("reorder ids must be a permutation of the page's layers")
            page["layers"] = [by_id[i] for i in op.layer_ids]
        elif isinstance(op, SetText):
            _require_layer(d, op.layer_id)["text"] = op.text
        elif isinstance(op, ReplaceImage):
            ly = _require_layer(d, op.layer_id)
            ly["asset_id"] = str(op.asset_id)
            ly.pop("crop", None)  # a new image invalidates the old crop region
        elif isinstance(op, ApplyBrandToken):
            _require_layer(d, op.layer_id)[op.field] = op.token
        elif isinstance(op, SetAnimation):
            _require_layer(d, op.layer_id)["animation"] = copy.deepcopy(op.animation)
        elif isinstance(op, SetBackground):
            _page(d, op.page_index)["background"] = copy.deepcopy(op.background)
        elif isinstance(op, AddPage):
            page = copy.deepcopy(op.page) if op.page is not None else {"layers": []}
            if op.at_index is None:
                d["pages"].append(page)
            else:
                d["pages"].insert(op.at_index, page)
        elif isinstance(op, DeletePage):
            if len(d["pages"]) <= 1:
                raise OpError("cannot delete the last page")
            _page(d, op.page_index)
            d["pages"].pop(op.page_index)
        else:  # pragma: no cover - exhaustive by the discriminated union
            raise OpError(f"unknown op {op!r}")
    return d
