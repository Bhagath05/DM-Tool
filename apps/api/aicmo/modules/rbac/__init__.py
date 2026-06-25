"""RBAC — permission-based authorisation.

Permissions are slugs ("brand.manage", "content.create"). Roles bundle
permissions. Members are assigned roles. The auth chain checks for the
presence of a specific permission slug; no code ever asks "is the user
an admin?" — it asks "does the user have campaign.create?"

This shape is enterprise-ready from day one. Custom roles per org (the
permission editor UI) is a Tier 4 feature; the schema already supports
it via `roles.organization_id IS NOT NULL`.
"""
