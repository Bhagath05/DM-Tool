"""The closed layer-document schema — the validation spine of the studio.

EVERY revision (AI Mode, Guided Mode, Pro Mode) is validated against this
before it is written (Law 3). The union of layer types is CLOSED — there is
no `html`/`raw`/`script` layer type — so neither a model nor a human can
inject unsafe content through any mode. Asset references must resolve to
tenant-owned assets (checked by `assert_tenant_refs` in the revision
engine); brand-bound props may carry a `brand:<token>` reference that is
resolved at render time.

Coordinates are normalized fractions of the canvas (0..1) so a design is
resolution- and format-independent.
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Semantic roles — OUTCOME/compositional, never industry (Law 2).
LayerRole = Literal[
    "background", "logo", "headline", "subhead", "body",
    "cta", "product", "decoration", "subtitle",
]

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_BRAND_TOKEN = re.compile(r"^brand:[a-z][a-z0-9_]{0,31}$")
_FONT_TOKEN = re.compile(r"^(?:brand:[a-z][a-z0-9_]{0,31}|[A-Za-z0-9 ,'\-]{1,64})$")


def _is_color(v: str) -> bool:
    return bool(_HEX.match(v) or _BRAND_TOKEN.match(v))


def _is_font(v: str) -> bool:
    return bool(_FONT_TOKEN.match(v))


class _Strict(BaseModel):
    """Base: forbid unknown fields. This is what makes the schema *closed* —
    an injected `<script>`/`html`/arbitrary key is rejected, not ignored."""

    model_config = ConfigDict(extra="forbid")


class Animation(_Strict):
    kind: Literal["none", "fade", "slide", "zoom", "pop", "wipe"] = "none"
    duration_ms: int = Field(default=400, ge=0, le=60000)
    delay_ms: int = Field(default=0, ge=0, le=60000)
    easing: Literal["linear", "ease", "ease_in", "ease_out", "ease_in_out"] = "ease"


class _LayerBase(_Strict):
    id: str = Field(min_length=1, max_length=64)
    role: LayerRole | None = None
    x: float = Field(default=0.0, ge=-0.5, le=1.5)
    y: float = Field(default=0.0, ge=-0.5, le=1.5)
    w: float = Field(default=1.0, gt=0.0, le=2.0)
    h: float = Field(default=1.0, gt=0.0, le=2.0)
    rotation: float = Field(default=0.0, ge=-360.0, le=360.0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    z: int = Field(default=0, ge=0, le=9999)
    locked: bool = False
    animation: Animation | None = None


class TextLayer(_LayerBase):
    type: Literal["text"] = "text"
    text: str = Field(default="", max_length=5000)
    font_family: str = Field(default="brand:body")
    font_size: float = Field(default=0.05, gt=0.0, le=1.0)  # fraction of canvas height
    color: str = Field(default="brand:ink")
    align: Literal["left", "center", "right", "justify"] = "left"
    weight: Literal["regular", "medium", "semibold", "bold"] = "regular"

    @field_validator("color")
    @classmethod
    def _color_ok(cls, v: str) -> str:
        if not _is_color(v):
            raise ValueError(f"invalid color {v!r} (use #hex or brand:<token>)")
        return v

    @field_validator("font_family")
    @classmethod
    def _font_ok(cls, v: str) -> str:
        if not _is_font(v):
            raise ValueError(f"invalid font_family {v!r}")
        return v


class Crop(_Strict):
    """The visible source rectangle (normalized 0..1). Smaller = zoomed in;
    x/y reposition. The original asset is never altered — crop is layer
    metadata, applied at render."""

    x: float = Field(default=0.0, ge=0.0, le=1.0)
    y: float = Field(default=0.0, ge=0.0, le=1.0)
    w: float = Field(default=1.0, gt=0.0, le=1.0)
    h: float = Field(default=1.0, gt=0.0, le=1.0)


class Mask(_Strict):
    kind: Literal["none", "circle", "rounded_rect"] = "none"
    radius: float = Field(default=0.0, ge=0.0, le=1.0)  # for rounded_rect


class ImageLayer(_LayerBase):
    type: Literal["image"] = "image"
    asset_id: uuid.UUID  # MUST reference a tenant-owned brand_asset / creative_asset
    fit: Literal["cover", "contain", "fill", "stretch"] = "cover"
    radius: float = Field(default=0.0, ge=0.0, le=1.0)
    crop: Crop | None = None
    mask: Mask | None = None


class IconLayer(_LayerBase):
    type: Literal["icon"] = "icon"
    icon_name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9\-]+$")
    color: str = Field(default="brand:ink")

    @field_validator("color")
    @classmethod
    def _color_ok(cls, v: str) -> str:
        if not _is_color(v):
            raise ValueError(f"invalid color {v!r}")
        return v


class ShapeLayer(_LayerBase):
    type: Literal["shape"] = "shape"
    shape: Literal["rect", "ellipse", "line"] = "rect"
    fill: str | None = Field(default="brand:primary")
    stroke: str | None = None
    stroke_width: float = Field(default=0.0, ge=0.0, le=0.2)
    radius: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("fill", "stroke")
    @classmethod
    def _color_ok(cls, v: str | None) -> str | None:
        if v is not None and not _is_color(v):
            raise ValueError(f"invalid color {v!r}")
        return v


class VideoLayer(_LayerBase):
    type: Literal["video"] = "video"
    asset_id: uuid.UUID
    trim_start_ms: int = Field(default=0, ge=0)
    trim_end_ms: int | None = Field(default=None, ge=0)
    muted: bool = False


class AudioLayer(_LayerBase):
    type: Literal["audio"] = "audio"
    asset_id: uuid.UUID
    gain: float = Field(default=1.0, ge=0.0, le=2.0)


class GroupLayer(_LayerBase):
    type: Literal["group"] = "group"
    children: list["Layer"] = Field(default_factory=list)


Layer = Annotated[
    Union[TextLayer, ImageLayer, IconLayer, ShapeLayer, VideoLayer, AudioLayer, GroupLayer],
    Field(discriminator="type"),
]

GroupLayer.model_rebuild()


class Background(_Strict):
    kind: Literal["color", "image", "none"] = "color"
    color: str = Field(default="brand:surface")
    asset_id: uuid.UUID | None = None

    @field_validator("color")
    @classmethod
    def _color_ok(cls, v: str) -> str:
        if not _is_color(v):
            raise ValueError(f"invalid color {v!r}")
        return v


class Page(_Strict):
    background: Background = Field(default_factory=Background)
    layers: list[Layer] = Field(default_factory=list, max_length=200)
    duration_ms: int | None = Field(default=None, ge=0, le=600000)


class LayerDoc(_Strict):
    """The whole editable document. The ONLY accepted shape for a revision."""

    version: int = Field(default=1, ge=1)
    format_slug: str | None = Field(default=None, max_length=48)
    # Display aspect ("1:1" | "4:5" | "9:16" | "16:9"). Optional + backward
    # compatible — old docs (no aspect) render at the viewer default.
    aspect: str | None = Field(default=None, max_length=8)
    pages: list[Page] = Field(default_factory=lambda: [Page()], min_length=1, max_length=50)


# ---------------------------------------------------------------------
#  Tenant-ownership of asset references (Law 3 security — no cross-tenant
#  refs). The set of owned ids is supplied by the revision engine (DB).
# ---------------------------------------------------------------------
def _walk_layers(layers: list[Layer]):
    for ly in layers:
        yield ly
        if isinstance(ly, GroupLayer):
            yield from _walk_layers(ly.children)


def collect_asset_refs(doc: LayerDoc) -> set[uuid.UUID]:
    refs: set[uuid.UUID] = set()
    for page in doc.pages:
        if page.background.asset_id is not None:
            refs.add(page.background.asset_id)
        for ly in _walk_layers(page.layers):
            aid = getattr(ly, "asset_id", None)
            if aid is not None:
                refs.add(aid)
    return refs


class CrossTenantAssetRef(ValueError):
    """A layer referenced an asset not owned by the design's tenant."""


def assert_tenant_refs(doc: LayerDoc, owned_asset_ids: set[uuid.UUID]) -> None:
    """Raise if the doc references any asset not in the tenant-owned set."""
    used = collect_asset_refs(doc)
    foreign = used - owned_asset_ids
    if foreign:
        raise CrossTenantAssetRef(
            f"design references {len(foreign)} asset(s) not owned by this tenant"
        )


def validate_doc(raw: dict[str, Any]) -> LayerDoc:
    """Validate an arbitrary dict against the closed schema. Raises
    pydantic.ValidationError on any violation (unknown key, bad color,
    raw-HTML layer type, out-of-bounds geometry, …)."""
    return LayerDoc.model_validate(raw)
