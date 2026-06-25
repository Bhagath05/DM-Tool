"""Publishing platform connection mapping tests."""

from __future__ import annotations

import pytest

from aicmo.modules.publishing.schemas import PublishPlatform


@pytest.mark.parametrize(
    "platform",
    [
        "instagram",
        "facebook",
        "linkedin",
        "youtube",
        "pinterest",
        "google_business_profile",
    ],
)
def test_publish_platform_literal_includes_all(platform: str) -> None:
    # Pydantic Literal membership — constructing a model validates the enum
    from aicmo.modules.publishing.schemas import SchedulePostRequest
    from datetime import UTC, datetime
    import uuid

    req = SchedulePostRequest(
        content_asset_id=uuid.uuid4(),
        platform=platform,  # type: ignore[arg-type]
        scheduled_at=datetime.now(UTC),
    )
    assert req.platform == platform
