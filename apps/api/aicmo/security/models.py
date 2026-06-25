from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base


class RateLimitBucket(Base):
    """Postgres-backed fixed-window rate limiter.

    One row per (key, window_start). Composite uniqueness lets us UPSERT
    cheaply. Cleanup happens opportunistically — see `rate_limit.cleanup_stale`.
    """

    __tablename__ = "rate_limit_buckets"
    __table_args__ = (
        UniqueConstraint("key", "window_start", name="uq_rl_key_window"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(255), index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
