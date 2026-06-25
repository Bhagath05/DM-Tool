/**
 * Coalesce identical in-flight GET requests within a short TTL window.
 *
 * Prevents duplicate LLM-backed calls when multiple sibling components
 * mount on the same page (e.g. AiCoachPanel + ThisWeekStrip both call
 * `/coach/weekly`). Does not cache errors.
 */

const inflight = new Map<string, Promise<unknown>>();
const recent = new Map<string, { value: unknown; expiresAt: number }>();

const DEFAULT_TTL_MS = 30_000;

export function dedupeRequest<T>(
  key: string,
  fn: () => Promise<T>,
  ttlMs: number = DEFAULT_TTL_MS,
): Promise<T> {
  const now = Date.now();
  const cached = recent.get(key);
  if (cached && cached.expiresAt > now) {
    return Promise.resolve(cached.value as T);
  }

  const pending = inflight.get(key);
  if (pending) return pending as Promise<T>;

  const promise = fn()
    .then((value) => {
      recent.set(key, { value, expiresAt: now + ttlMs });
      return value;
    })
    .finally(() => {
      inflight.delete(key);
    });

  inflight.set(key, promise);
  return promise;
}

/** Test-only: reset module state between tests. */
export function __resetRequestDedupeForTests(): void {
  inflight.clear();
  recent.clear();
}
