"""P0-1 — backup + restore verification.

Runs the real `verify_restore.sh` (backup → restore into a scratch db →
compare → drop). Skipped when docker / the postgres container isn't
available so the unit suite still passes in CI without a DB.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]  # repo root
_VERIFY = _ROOT / "infra" / "backup" / "verify_restore.sh"


def _docker_pg_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        return "ai-cmo-postgres" in out.stdout
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _VERIFY.exists(), reason="verify_restore.sh missing")
@pytest.mark.skipif(not _docker_pg_up(), reason="docker postgres not running")
def test_backup_is_restorable():
    """A fresh backup restores into a scratch DB with identical table count,
    org count, and migration head — proving backups are usable."""
    proc = subprocess.run(
        ["bash", str(_VERIFY)], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, f"verify_restore failed:\n{proc.stdout}\n{proc.stderr}"
    assert "PASS" in proc.stdout
