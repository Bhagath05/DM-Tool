from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from aicmo.config import get_settings
from aicmo.db.base import Base

# Import every feature module's ORM model so Alembic --autogenerate sees them.
from aicmo.modules.ads.models import GeneratedAd  # noqa: F401, E402
from aicmo.modules.advisor.models import (  # noqa: F401, E402
    AdvisorMemoryEvent,
    AdvisorRecommendation,
)
from aicmo.modules.ai_audit.models import AiAuditEvent  # noqa: F401, E402
from aicmo.modules.creative.models import (  # noqa: F401, E402
    BrandKit,
    CreativeAsset,
    CreativeCostEvent,
    CreativeExport,
    CreativeFormat,
    CreativeProject,
    CreativeTemplate,
    CreativeVariant,
)
from aicmo.modules.video.models import VideoRender, VideoScene  # noqa: F401, E402
from aicmo.modules.creative.design.models import (  # noqa: F401, E402
    BrandAsset,
    CreativeDesign,
    CreativeDesignRevision,
)
from aicmo.modules.growth.models import (  # noqa: F401, E402
    GrowthObjective,
    LayoutPrimitive,
    ObjectiveKind,
)
from aicmo.modules.audit.models import AuditEvent  # noqa: F401, E402
from aicmo.modules.brands.models import Brand  # noqa: F401, E402
from aicmo.modules.bundles.models import Bundle  # noqa: F401, E402
from aicmo.modules.campaigns.models import CampaignPlan  # noqa: F401, E402
from aicmo.modules.content.models import GeneratedContent  # noqa: F401, E402
from aicmo.modules.landing_pages.models import LandingPage  # noqa: F401, E402
from aicmo.modules.leads.models import Lead  # noqa: F401, E402
from aicmo.modules.learning.models import (  # noqa: F401, E402
    CampaignExperiment,
    ExperimentResult,
    LearningEvent,
)
from aicmo.modules.onboarding.models import BusinessProfile  # noqa: F401, E402
from aicmo.modules.orgs.models import (  # noqa: F401, E402
    MemberRole,
    Organization,
    OrganizationMember,
)
from aicmo.modules.integrations.models import (  # noqa: F401, E402
    IntegrationConnection,
    IntegrationCredential,
)
from aicmo.modules.notifications.models import (  # noqa: F401, E402
    NotificationPreference,
)
from aicmo.modules.security.models import (  # noqa: F401, E402
    SecurityEvent,
    UserSession,
)
from aicmo.modules.team.models import (  # noqa: F401, E402
    OrganizationInvite,
)
from aicmo.modules.billing.plan_models import (  # noqa: F401, E402
    Plan,
    PlanQuota,
    StripeEvent,
)
from aicmo.modules.billing.models import (  # noqa: F401, E402
    BillingUpgradeRequest,
    Invoice,
    Subscription,
    UsageEvent,
)
from aicmo.modules.performance.models import (  # noqa: F401, E402
    CreativeResult,
    PerformanceDiagnostic,
    PerformanceEvent,
)
from aicmo.modules.publishing.models import (  # noqa: F401, E402
    ContentAsset,
    PublishEvent,
    ScheduledPost,
)
from aicmo.modules.rbac.models import (  # noqa: F401, E402
    Permission,
    Role,
    RolePermission,
)
from aicmo.modules.social.models import (  # noqa: F401, E402
    AudiencePattern,
    PerformanceSignal,
    SocialAsset,
    SocialConnection,
    WinningPattern,
)
from aicmo.modules.trends.models import TrendReport  # noqa: F401, E402
from aicmo.modules.users.models import User  # noqa: F401, E402
from aicmo.modules.visuals.models import GeneratedVisual  # noqa: F401, E402
from aicmo.modules.visuals.render_models import RenderedVisual  # noqa: F401, E402
from aicmo.security.models import RateLimitBucket  # noqa: F401, E402

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
