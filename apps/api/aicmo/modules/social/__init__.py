"""Social Intelligence Layer — Phase 1.

READ-ONLY by design. Social APIs are *intelligence sources* here, not
publishing pipes. This module pulls down a creator's existing posts +
performance metrics, derives winning patterns, and feeds those patterns
back into every generator via GenerationContext.

What we deliberately don't do (yet, per directive):
- auto-posting
- scheduling
- automated comments / DMs
- multi-agent planners
- background queue automation

When (and if) we add publishing, it lives in a separate module —
distribution / publishing — not here. This package stays an analytics
input.
"""
