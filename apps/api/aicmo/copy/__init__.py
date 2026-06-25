"""Shared copy-tone enforcement.

One source of truth for what the platform sounds like. Every generator's
prompt should import `TONE_GUARDRAILS` and embed it in the system prompt —
this way fixing "the LLM keeps saying 'unlock growth'" is a one-line edit
that hits content, ads, visuals, campaigns, bundles, and the coach modules
simultaneously.

Also provides post-generation utilities (`scrub_text`) and render-prompt
sanitisers (`strip_overlay_text_instructions`) so we can clean up outputs
the LLM still produces despite the guardrails.

`MarketingCreativeBrief` and `CREATIVE_BRIEF_INSTRUCTION` live in
`creative_brief.py` — every generator embeds the brief contract in its
system prompt so assets ship with objective, audience, hook, offer, CTA,
visual direction, and platform.
"""
