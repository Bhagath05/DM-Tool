import type { Route } from "next";

/**
 * Builds a redirect target for a legacy route shim, forwarding any query string
 * so deep-links (e.g. the `?from=` source banner, draft seeds) keep working as
 * they move to the canonical route.
 *
 * Returns a `Route` (typed-routes) built from a dynamic string — the cast is the
 * repo convention for runtime-built hrefs. Presentation/navigation only: no
 * auth, tenant, or Trust logic here.
 */
export function legacyTarget(
  canonical: string,
  searchParams: Record<string, string | string[] | undefined>,
): Route {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (typeof value === "string") qs.set(key, value);
    else if (Array.isArray(value)) value.forEach((v) => qs.append(key, v));
  }
  const q = qs.toString();
  return (q ? `${canonical}?${q}` : canonical) as Route;
}
