from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from aicmo.config import get_settings
from aicmo.db.base import Base

# Import every feature module's ORM model so Alembic --autogenerate sees them.
from aicmo.modules.ads.models import GeneratedAd  # noqa: F401
from aicmo.modules.advisor.models import (  # noqa: F401
    AdvisorMemoryEvent,
    AdvisorRecommendation,
)
from aicmo.modules.ai_audit.models import AiAuditEvent  # noqa: F401
from aicmo.modules.audit.models import AuditEvent  # noqa: F401
from aicmo.modules.billing.models import (  # noqa: F401
    BillingUpgradeRequest,
    Invoice,
    Subscription,
    UsageEvent,
)
from aicmo.modules.billing.plan_models import (  # noqa: F401
    Plan,
    PlanQuota,
    StripeEvent,
)
from aicmo.modules.brands.models import Brand  # noqa: F401
from aicmo.modules.bundles.models import Bundle  # noqa: F401
from aicmo.modules.campaigns.models import CampaignPlan  # noqa: F401
from aicmo.modules.content.models import GeneratedContent  # noqa: F401
from aicmo.modules.creative.design.models import (  # noqa: F401
    BrandAsset,
    CreativeDesign,
    CreativeDesignRevision,
)
from aicmo.modules.creative.models import (  # noqa: F401
    BrandKit,
    CreativeAsset,
    CreativeCostEvent,
    CreativeExport,
    CreativeFormat,
    CreativeProject,
    CreativeTemplate,
    CreativeVariant,
)
from aicmo.modules.growth.models import (  # noqa: F401
    GrowthObjective,
    LayoutPrimitive,
    ObjectiveKind,
)
from aicmo.modules.integrations.models import (  # noqa: F401
    IntegrationConnection,
    IntegrationCredential,
    IntegrationEvent,
)
from aicmo.modules.landing_pages.models import LandingPage  # noqa: F401
from aicmo.modules.leads.models import Lead  # noqa: F401
from aicmo.modules.autonomy.models import AutonomyPolicy  # noqa: F401
from aicmo.modules.operations.models import (  # noqa: F401
    DetectedEvent,
    MetricSnapshot,
    OperationalGoal,
    OperationsNotification,
    OperationsRun,
    ScheduledWork,
)
from aicmo.modules.learning.models import (  # noqa: F401
    CampaignExperiment,
    ExperimentResult,
    LearningEvent,
    LearningInsight,
)
from aicmo.modules.notifications.models import (  # noqa: F401
    NotificationPreference,
)
from aicmo.modules.onboarding.models import BusinessProfile  # noqa: F401
from aicmo.modules.orgs.models import (  # noqa: F401
    MemberRole,
    Organization,
    OrganizationMember,
)
from aicmo.modules.performance.models import (  # noqa: F401
    CreativeResult,
    PerformanceDiagnostic,
    PerformanceEvent,
)
from aicmo.modules.publishing.models import (  # noqa: F401
    ContentAsset,
    PublishEvent,
    ScheduledPost,
)
from aicmo.modules.rbac.models import (  # noqa: F401
    Permission,
    Role,
    RolePermission,
)
from aicmo.modules.security.models import (  # noqa: F401
    SecurityEvent,
    UserSession,
)
from aicmo.modules.social.models import (  # noqa: F401
    AudiencePattern,
    PerformanceSignal,
    SocialAsset,
    SocialConnection,
    WinningPattern,
)
from aicmo.modules.strategist.models import (  # noqa: F401
    MarketingStrategyRecord,
)
from aicmo.modules.team.models import (  # noqa: F401
    OrganizationInvite,
)
from aicmo.modules.trends.models import TrendReport  # noqa: F401
from aicmo.modules.users.models import User  # noqa: F401
from aicmo.modules.video.models import VideoRender, VideoScene  # noqa: F401
from aicmo.modules.visuals.models import GeneratedVisual  # noqa: F401
from aicmo.modules.visuals.render_models import RenderedVisual  # noqa: F401
from aicmo.security.models import RateLimitBucket  # noqa: F401
from alembic import context

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
