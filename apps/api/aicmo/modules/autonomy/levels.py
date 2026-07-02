"""Module 10 — Future Autonomy Flags: progressive autonomy LEVELS.

A level is a one-click PRESET over the Module 9 per-action policy — the ladder a
customer climbs to give the AI more autonomy over time. Applying a level writes
the corresponding per-action modes into the policy; the admin can still fine-tune
any single action afterwards (Module 9).

Nothing here bypasses the safety model: even at `full`, the global master switch
(`autonomy_execution_enabled`, default OFF) still gates real auto-execution.
"""

from __future__ import annotations

# Ordered ladder. Each level maps to a default_mode + per-action overrides.
# Actions not listed inherit default_mode.
_LEVELS: dict[str, dict] = {
    "manual": {
        "order": 0,
        "label": "Manual",
        "description": "The AI drafts and advises; you approve and trigger everything. Nothing is automated.",
        "default_mode": "always_approve",
        "policies": {},
    },
    "assisted": {
        "order": 1,
        "label": "Assisted",
        "description": "The AI freely generates drafts, ideas, recommendations, and decisions. Publishing, sending, and spending still need your approval.",
        "default_mode": "always_approve",
        "policies": {
            "content_generation": "auto_always",
            "image_generation": "auto_always",
            "ai_recommendation": "auto_always",
            "ai_decision": "auto_always",
        },
    },
    "scheduled": {
        "order": 2,
        "label": "Scheduled autonomy",
        "description": "Everything in Assisted, plus the AI assembles campaigns and publishes/sends automatically during your business hours. Spending still needs approval.",
        "default_mode": "always_approve",
        "policies": {
            "content_generation": "auto_always",
            "image_generation": "auto_always",
            "ai_recommendation": "auto_always",
            "ai_decision": "auto_always",
            "campaign_creation": "auto_always",
            "ad_creation": "auto_always",
            "crm_update": "auto_always",
            "social_publishing": "auto_business_hours",
            "campaign_launch": "auto_business_hours",
            "email_sending": "auto_business_hours",
        },
    },
    "supervised": {
        "order": 3,
        "label": "Supervised autonomy",
        "description": "Broad autonomy: the AI runs most actions itself, spending automatically only under thresholds you set. Above a threshold it still asks.",
        "default_mode": "auto_always",
        "policies": {
            "budget_change": "auto_below_threshold",
            "ad_spending": "auto_below_threshold",
        },
    },
    "full": {
        "order": 4,
        "label": "Full autonomy",
        "description": "The AI runs the whole marketing loop end to end. (The platform master switch must also be enabled for anything to actually auto-run.)",
        "default_mode": "auto_always",
        "policies": {},
    },
}


def is_level(level: str) -> bool:
    return level in _LEVELS


def preset_for(level: str) -> tuple[str, dict[str, str]]:
    """(default_mode, {action_type: mode}) for a level. Falls back to the safe
    'manual' preset for an unknown level."""
    spec = _LEVELS.get(level) or _LEVELS["manual"]
    return spec["default_mode"], dict(spec["policies"])


def catalog() -> list[dict]:
    """Ordered level descriptions for the settings UI."""
    return [
        {
            "key": key,
            "order": spec["order"],
            "label": spec["label"],
            "description": spec["description"],
        }
        for key, spec in sorted(_LEVELS.items(), key=lambda kv: kv[1]["order"])
    ]
