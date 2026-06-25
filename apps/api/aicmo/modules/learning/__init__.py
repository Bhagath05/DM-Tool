"""Learning Lab — Phase 1B of the platform intelligence stack.

Three tables, one mental model:

- **CampaignExperiment** — a provenance row written every time a generator
  produces an asset. Captures the *hypothesis* (what we expected to work
  and why), the patterns we inherited from Social Intelligence, and the
  concrete variable choices (hook style, format, tone, platform).
- **ExperimentResult** — the performance snapshot pulled back from
  analytics once the asset has been distributed. One experiment can have
  multiple results over time (we re-snapshot weekly).
- **LearningEvent** — an evidence-backed insight the Learning Engine
  derives from a cluster of experiments + results. These are what feed
  back into the GenerationContext so the next batch of asks gets better.

Why these three live in their own module (not stuffed into `social/`):
Social Intelligence answers "what already works on this user's posts?"
Learning Lab answers "what worked AMONG THE THINGS WE GENERATED?" The
inputs, attribution chain, and feedback loop are different — keep them
testable independently.
"""
