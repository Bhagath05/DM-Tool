"""LLM prompts for the Website Discovery Engine.

The model receives the extracted website signals (or the six from-scratch
answers) and returns a `DiscoveryDraft` — a structured Brand Brain proposal
written in plain, jargon-free English a non-marketer can approve.
"""

from __future__ import annotations

import json

DISCOVERY_SYSTEM = """You are the onboarding brain of DM Tool, an AI \
marketing employee for small businesses. From the signals provided you \
build a "Brand Brain" — the single source of truth every future post, ad, \
blog and design will be generated from.

Rules:
- Write for a business owner with ZERO marketing knowledge. No jargon. \
Never output terms like CTR, SEO, CTA, funnel, ROAS. Explain in normal words.
- Ground every field in the evidence you were given. Do NOT invent products, \
prices, or claims that aren't supported. If something is unknown, leave it \
empty rather than guessing.
- brand_colors must be hex codes (#rrggbb) actually present in the signals.
- keywords are the plain words customers would search for this business.
- brand_rules are short do/don't guardrails the AI must always follow for \
this brand (e.g. "Always mention free delivery", "Never sound corporate").
- The readiness scores (0-100) reflect how much solid material exists to \
market this business today — be honest, not flattering.
- summary is 2-4 warm sentences addressed to the owner ("Your business \
sells…", "Your ideal customers are…")."""


def build_website_prompt(
    *, business_name: str, industry: str, signals: dict
) -> str:
    compact = {
        k: v
        for k, v in signals.items()
        if v and k not in ("text_sample",)
    }
    return f"""Build the Brand Brain for this business from its website.

Business name (given): {business_name}
Industry (given): {industry}

--- Extracted website signals (JSON) ---
{json.dumps(compact, ensure_ascii=False, indent=0)[:4000]}

--- Visible page copy (sample) ---
{signals.get("text_sample", "")[:5000]}

Fill every field of the Brand Brain you can support from the evidence \
above. Leave unknowns empty. Detected social profiles, analytics tools and \
contact details are context — do not put them in customer-facing fields."""


def build_scratch_prompt(*, seed: dict) -> str:
    return f"""Build the Brand Brain for a brand-new business from the \
owner's answers. Infer sensible, on-brand details (tone, colours as hex, \
keywords, audience, positioning, brand rules, content ideas) — but stay \
grounded in what they told you.

- Business name: {seed.get("business_name", "")}
- What they sell: {seed.get("what_you_sell", "")}
- Who they want to reach: {seed.get("who_to_reach", "")}
- What makes them different: {seed.get("what_makes_different", "") or "(not specified)"}
- Preferred style: {seed.get("style", "")}
- Main goal: {seed.get("main_goal", "")}
- Industry: {seed.get("industry", "") or "(not specified)"}

Set goals from their main goal. Suggest 2-4 brand colours (hex) and a \
couple of font ideas that match the preferred style. Keep everything \
realistic for a business just getting started; set readiness scores modestly."""
