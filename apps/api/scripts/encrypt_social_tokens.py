"""One-time back-fill: encrypt any plaintext social OAuth tokens at rest.

Idempotent — Fernet ciphertext is detected by its `gAAAAA` prefix and
skipped, so re-running is safe. Requires `INTEGRATION_TOKEN_KEY` to be set.

Run:
    cd apps/api && python -m scripts.encrypt_social_tokens          # apply
    cd apps/api && python -m scripts.encrypt_social_tokens --dry-run
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from aicmo.config import get_settings
from aicmo.db.session import SessionLocal, engine
from aicmo.modules.social.models import SocialConnection
from aicmo.modules.social.token_crypto import looks_encrypted, seal


async def run(dry_run: bool) -> int:
    if not get_settings().integration_token_key.strip():
        print("ERROR: INTEGRATION_TOKEN_KEY is not set — cannot encrypt.", file=sys.stderr)
        return 2

    changed = 0
    scanned = 0
    async with SessionLocal() as session:
        rows = (await session.execute(select(SocialConnection))).scalars().all()
        for row in rows:
            scanned += 1
            dirty = False
            for field in ("access_token", "refresh_token"):
                val = getattr(row, field)
                if val and not looks_encrypted(val):
                    if not dry_run:
                        setattr(row, field, seal(val))
                    dirty = True
            if dirty:
                changed += 1
        if not dry_run:
            await session.commit()
    await engine.dispose()
    verb = "would encrypt" if dry_run else "encrypted"
    print(f"scanned={scanned} connections; {verb} tokens on {changed} rows.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run("--dry-run" in sys.argv)))
