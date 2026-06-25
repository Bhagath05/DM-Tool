"""Brands — second-level tenant; owns business data.

Every business row in the system carries `brand_id`. Brand isolation is
the actual data security boundary; org isolation is the team/billing
boundary. In Tier 1 every org has exactly one brand (auto-created at
onboarding); the brand switcher in the UI only appears when an org has
≥2 brands. The schema supports unlimited brands per org.
"""
