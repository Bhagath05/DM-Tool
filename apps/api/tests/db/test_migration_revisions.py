"""Regression guards for the Alembic revision graph.

Ships because a real deploy-breaking bug slipped through: revision id
``0070_social_asset_provider_content`` (34 chars) exceeded the width of
Alembic's ``alembic_version.version_num`` column (``VARCHAR(32)``), so the
final ``UPDATE alembic_version SET version_num=...`` raised
``StringDataRightTruncation`` and ``alembic upgrade head`` failed on every
fresh database — while pure-Python tests (which never touch Postgres) stayed
green. These tests catch the whole class of graph defects without a DB.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

# Alembic's default ``alembic_version.version_num`` column width. A revision
# identifier longer than this cannot be recorded, so the migration is
# unappliable no matter how correct its DDL is.
VERSION_NUM_MAX_LEN = 32

_API_ROOT = Path(__file__).resolve().parents[2]


def _script_directory() -> ScriptDirectory:
    cfg = Config(str(_API_ROOT / "alembic.ini"))
    # Resolve script_location relative to the api root, independent of CWD.
    cfg.set_main_option("script_location", str(_API_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_all_revision_ids_fit_version_num_column() -> None:
    """Every revision id must fit ``alembic_version.version_num VARCHAR(32)``."""
    script = _script_directory()
    offenders = {
        rev.revision: len(rev.revision)
        for rev in script.walk_revisions()
        if len(rev.revision) > VERSION_NUM_MAX_LEN
    }
    assert not offenders, (
        "Revision id(s) exceed VARCHAR(32) and will break `alembic upgrade` on a "
        f"fresh DB with StringDataRightTruncation: {offenders}"
    )


def test_single_linear_head() -> None:
    """Exactly one head — an accidental branch also breaks `upgrade head`."""
    script = _script_directory()
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected a single migration head, found: {heads}"


def test_revision_graph_is_walkable() -> None:
    """Every down_revision resolves (no dangling parent references)."""
    script = _script_directory()
    # walk_revisions() from base to head raises if the chain is broken.
    revisions = list(script.walk_revisions())
    assert revisions, "No Alembic revisions discovered"
