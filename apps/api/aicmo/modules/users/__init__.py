"""Users — our canonical user row, mirroring Clerk identity.

Why our own table rather than reading Clerk on every request: Clerk's
`sub` claim gives us a stable user identity, but every downstream entity
(memberships, audit, attribution) needs an FK target. A `clerk_user_id`
string column isn't an FK; a `users.id` UUID is. We mirror just enough
identity (email + display name) to drive UI without round-tripping.
"""
