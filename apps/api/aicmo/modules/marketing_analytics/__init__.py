"""Marketing analytics — the normalized layer over ConnectorMetric.

Phase 3. Turns the raw, provider-specific `ConnectorMetric` snapshots that the
Phase 2 collection cron accumulates into a normalized, honest analytics surface
that the Performance Marketer reasons over:

    ConnectorMetric (raw provider snapshots)
        → normalize.py   (canonical metric family + semantic kind)
        → timeseries.py  (day/week/month buckets, period-over-period compare)
        → sufficiency.py (how much can we honestly claim?)
        → rules.py       (deterministic, evidence-grounded insights)
        → service.py     (Performance Marketer report; LLM explains, never invents)

Adds NO new table — it is a read-only projection of `ConnectorMetric`. Never
fabricates a metric a provider did not report, and never claims a trend the
available data cannot support.
"""
