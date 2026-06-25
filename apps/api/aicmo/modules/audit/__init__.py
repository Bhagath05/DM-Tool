"""Audit — append-only record of every administrative mutation.

Wrote first, read later. The writer is wired into orgs/brands/rbac
service mutations now. A reader UI ships in a later slice (the data is
queryable via SQL until then).

Audit events that missed at the start cannot be backfilled — that's why
the writer is in scope today even though the reader isn't.
"""
