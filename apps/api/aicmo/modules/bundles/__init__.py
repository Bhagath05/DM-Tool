"""Campaign Bundle Engine — Phase 3.1.

Composition layer over the existing generators (content / ads / visuals /
campaigns). A bundle is N coordinated assets that share campaign theme,
audience, and tone via the shared GenerationContext. No new generation
logic — just parallel orchestration + a tiny linking table.

The bundle row stores REFERENCES to generated assets (their UUIDs).
Each asset lives in its own existing table; we don't duplicate content.
"""
