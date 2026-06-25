"""Context module — Phase 3.0.

A shared computation layer that snapshots everything the platform already
knows about a user (profile + intelligence-engine output + winning patterns
+ reality constraints) into one object. Every generator can opt in to
inherit this snapshot, so the frontend stops asking the user the same
questions every studio.

The module reads from existing services and persists nothing — it's pure
composition over what's already there. Touching it is rollback-safe by
construction.
"""
