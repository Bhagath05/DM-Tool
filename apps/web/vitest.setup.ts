import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

/**
 * Vitest global setup — runs once before the test suite.
 *
 * - Pulls in `@testing-library/jest-dom` matchers (`toBeInTheDocument`, ...).
 * - Wires automatic DOM cleanup between tests so a leftover provider
 *   from one test doesn't pollute the next.
 * - Provides a no-op `next/navigation` mock by default; individual tests
 *   can override via `vi.doMock` if they need to assert on `push()` calls.
 */

afterEach(() => {
  cleanup();
});

// next/navigation isn't available outside a Next.js request context.
// Default to a no-op stub. Tests that care about router behaviour
// re-mock this with vi.doMock at the top of the file.
//
// CRITICAL: useRouter() must return a STABLE reference across calls.
// Provider hooks (e.g. TenantProvider) put the router in a useCallback
// dep array; returning a fresh object every render makes useCallback
// deps churn → useEffect re-fires → infinite render loop.
const _stableRouter = {
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  prefetch: vi.fn(),
};
const _stableSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => _stableRouter,
  usePathname: () => "/",
  useSearchParams: () => _stableSearchParams,
}));
