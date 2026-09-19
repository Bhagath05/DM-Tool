"use client";

/**
 * First-party auth provider.
 *
 * Authentication is a backend concern: the session lives in an HttpOnly cookie
 * and `TenantProvider`'s `GET /users/me` call is the single source of truth for
 * who is signed in. There is deliberately no separate frontend auth state
 * machine and no third-party auth SDK — this component simply renders its
 * children. It is kept as a stable mount point in the layout tree.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
