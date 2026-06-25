"""CS1-7 — Law 2 guard (no template categories / no industry hardcoding) +
the growth.* RBAC grant matrix.

The guard AST-scans the CS1 source (growth + creative/design + the migration
seeds) for industry tokens appearing as *string literals in code* — i.e.
control-flow branches, dict keys, or seed data. Comments and docstrings are
intentionally NOT scanned: industry is allowed as free-text *prompt context*,
just never as a code dimension.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest

# Industries that must never appear as code literals in the studio.
INDUSTRY_TOKENS = frozenset({
    "restaurant", "restaurants", "healthcare", "hospital", "clinic", "dental",
    "dentist", "fitness", "gym", "salon", "realtor", "realestate", "ecommerce",
    "retail", "saas", "insurance", "automotive", "manufacturing", "hospitality",
    "consulting", "recruitment", "plumber", "electrician", "lawyer", "accounting",
    "mortgage", "veterinary", "education",
})

_API_ROOT = Path(__file__).resolve().parents[1].parent  # apps/api
_SCAN_DIRS = [
    _API_ROOT / "aicmo" / "modules" / "growth",
    _API_ROOT / "aicmo" / "modules" / "creative" / "design",
]
_SCAN_FILES = [
    _API_ROOT / "alembic" / "versions" / "0035_creative_studio.py",
]


def _docstring_node_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), ast.Constant
            ) and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def find_industry_literals(source: str) -> list[str]:
    """Return industry tokens found in non-docstring string literals (code)."""
    tree = ast.parse(source)
    skip = _docstring_node_ids(tree)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            low = node.value.lower()
            for tok in INDUSTRY_TOKENS:
                if re.search(rf"\b{re.escape(tok)}\b", low):
                    hits.append(tok)
    return hits


# ---- the guard catches a planted violation ----
@pytest.mark.parametrize("snippet", [
    'if industry == "restaurant":\n    pass',
    'TEMPLATES = {"healthcare": [], "retail": []}',
    'kind = "saas"',
])
def test_guard_flags_industry_in_code(snippet):
    assert find_industry_literals(snippet), "guard must flag industry code literals"


def test_guard_ignores_docstrings_and_comments():
    # industry words in a docstring / comment are allowed (prompt context)
    src = '"""Serves restaurant, healthcare, retail with one code path."""\nx = 1  # saas too\n'
    assert find_industry_literals(src) == []


# ---- the real CS1 surface is clean ----
def _iter_sources():
    for d in _SCAN_DIRS:
        for p in d.rglob("*.py"):
            yield p
    for f in _SCAN_FILES:
        yield f


def test_cs1_sources_have_no_industry_literals():
    offenders: list[str] = []
    for path in _iter_sources():
        hits = find_industry_literals(path.read_text())
        if hits:
            offenders.append(f"{path.name}: {sorted(set(hits))}")
    assert offenders == [], f"Law-2 violation — industry literals in code: {offenders}"


# ---- growth.* RBAC grant matrix (pinned against the migration) ----
def _load_migration():
    path = _SCAN_FILES[0]
    spec = importlib.util.spec_from_file_location("mig_0035", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_growth_permissions_and_grants():
    mig = _load_migration()
    perm_slugs = {p[0] for p in mig._PERMISSIONS}
    assert perm_slugs == {"growth.create", "growth.read"}
    grants = set(mig._GRANTS)
    # create → owner/admin/editor; read → all five system roles
    for role in ("owner", "admin", "editor"):
        assert (role, "growth.create") in grants
    for role in ("owner", "admin", "editor", "analyst", "viewer"):
        assert (role, "growth.read") in grants
    # viewer/analyst must NOT be able to create
    assert ("viewer", "growth.create") not in grants
    assert ("analyst", "growth.create") not in grants


# ---- Law 3 guard: design.doc is assigned ONLY in the revision engine ----
_DOC_ASSIGN = re.compile(r"\.doc\s*=\s*(?!=)")


def test_no_direct_doc_mutation_outside_revision_engine():
    """The head doc may be written only through apply_revision (revision.py).
    Any `.doc =` assignment elsewhere in the design package is a Law-3 breach."""
    design_dir = _API_ROOT / "aicmo" / "modules" / "creative" / "design"
    offenders: list[str] = []
    for path in design_dir.rglob("*.py"):
        if path.name == "revision.py":
            continue  # the ONE sanctioned writer
        for i, line in enumerate(path.read_text().splitlines(), start=1):
            code = line.split("#", 1)[0]  # ignore trailing comments
            if _DOC_ASSIGN.search(code):
                offenders.append(f"{path.name}:{i}: {line.strip()}")
    assert offenders == [], f"Law-3 violation — direct design.doc mutation: {offenders}"
