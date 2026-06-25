/**
 * Inline profile validation — strategist tone, not compiler tone.
 *
 * Every helper returns `{ ok, hint? }`. Callers render `hint` as a soft
 * inline note (muted text), NOT a red error. The user can still proceed;
 * the hint is a nudge, not a wall. The backend (Pydantic validators in
 * `modules/onboarding/schemas.py`) is the real gate — these helpers
 * just save the user a round-trip to discover their input is too vague.
 *
 * Mirrors the backend's detectors so the two stay in lockstep. If you
 * change a rule here, change it there.
 */

export type ValidationResult = { ok: true } | { ok: false; hint: string };

// ----------------------------------------------------------------------
//  Generic / gibberish lists — keep in sync with the Python side.
// ----------------------------------------------------------------------

const GENERIC_AUDIENCE = new Set<string>([
  "everyone",
  "anyone",
  "all",
  "all audience",
  "all audiences",
  "all ages",
  "all people",
  "general public",
  "the public",
  "customers",
  "people",
  "humans",
  "viral",
  "viral audience",
  "mass market",
  "the world",
  "global",
  "n/a",
  "none",
  "tbd",
]);

const GENERIC_INDUSTRY = new Set<string>([
  "business",
  "company",
  "startup",
  "thing",
  "stuff",
  "n/a",
  "none",
  "tbd",
  "other",
  "general",
]);

// ----------------------------------------------------------------------
//  Gibberish heuristic — same rules as backend.
// ----------------------------------------------------------------------

export function looksLikeGibberish(text: string): boolean {
  const t = text.trim().toLowerCase();
  if (t.length < 2) return true;

  // Same letter repeats 5+ times in a row.
  if (/(.)\1{4,}/.test(t)) return true;

  // Mostly non-letters (digits / symbols).
  const letterCount = [...t].filter((c) => /[a-z]/i.test(c)).length;
  if (letterCount < Math.max(2, Math.floor(t.length / 2))) return true;

  // Long single-token strings with no vowels in the first chunk.
  if (!/\s|-/.test(t) && t.length > 8) {
    const head = t.slice(0, 8);
    if (!/[aeiouy]/.test(head)) return true;
  }

  return false;
}

export function isUltraGenericAudience(text: string): boolean {
  const t = text.trim().toLowerCase().replace(/[.!]+$/, "");
  if (GENERIC_AUDIENCE.has(t)) return true;
  // Single short token is almost always too generic.
  if (!t.includes(" ") && t.length < 16) return true;
  return false;
}

// ----------------------------------------------------------------------
//  Public validators
// ----------------------------------------------------------------------

export function validateBusinessName(name: string): ValidationResult {
  const t = name.trim();
  if (t.length === 0) return { ok: true }; // empty is "not yet" — handled by required-field UI
  if (t.length < 2) {
    return { ok: false, hint: "Add a bit more — even just the brand name works." };
  }
  if (looksLikeGibberish(t)) {
    return {
      ok: false,
      hint: "That doesn't look like a business name yet — give us what you actually call it.",
    };
  }
  return { ok: true };
}

export function validateIndustry(industry: string): ValidationResult {
  const t = industry.trim();
  if (t.length === 0) return { ok: true };
  if (looksLikeGibberish(t)) {
    return {
      ok: false,
      hint: "Try something specific — e.g. 'Cafe', 'B2B SaaS', 'Yoga studio'.",
    };
  }
  if (GENERIC_INDUSTRY.has(t.toLowerCase())) {
    return {
      ok: false,
      hint: `'${t}' is too generic — what KIND? e.g. 'Cafe', 'B2B SaaS', 'Local plumber'.`,
    };
  }
  return { ok: true };
}

export function validateAudience(audience: string): ValidationResult {
  const t = audience.trim();
  if (t.length === 0) return { ok: true };
  if (t.length < 10) {
    return {
      ok: false,
      hint: `${10 - t.length} more characters — a full sentence works best.`,
    };
  }
  if (looksLikeGibberish(t)) {
    return {
      ok: false,
      hint: "Try being more specific about who buys from you most.",
    };
  }
  if (isUltraGenericAudience(t)) {
    return {
      ok: false,
      hint: "'Everyone' isn't an audience — describe who actually buys (age, role, what they care about).",
    };
  }
  return { ok: true };
}

// ----------------------------------------------------------------------
//  Cross-field sanity (traction-vs-goal, platform-vs-industry).
//  These are softer — surface as advisory hints, never block submit.
// ----------------------------------------------------------------------

/** Look for "1 million" / "10x" / "viral" in goal text when stage is pre-traction. */
export function validateTractionVsGoal(
  leadsBand: string | null | undefined,
  goalText: string | null | undefined,
): ValidationResult {
  if (!leadsBand || !goalText) return { ok: true };
  const earlyStages = new Set(["starting", "1-50"]);
  if (!earlyStages.has(leadsBand)) return { ok: true };

  const g = goalText.toLowerCase();
  const moonshot =
    /\b(million|10x|100x|viral|overnight|dominate|world)\b/.test(g) ||
    /\b(100k|500k|1m)\b/.test(g);
  if (!moonshot) return { ok: true };

  return {
    ok: false,
    hint:
      "Big goal for an early-stage business — the Reality Engine will keep us honest later, but a more concrete near-term outcome usually works better here.",
  };
}

/** Soft warning when chosen platforms don't fit the industry shape. */
export function validatePlatformRelevance(
  industry: string | null | undefined,
  platforms: string[],
): ValidationResult {
  if (!industry || platforms.length === 0) return { ok: true };
  const ind = industry.toLowerCase();
  const platformSet = new Set(platforms.map((p) => p.toLowerCase()));

  // Local consumer-facing businesses on LinkedIn-only = mismatch.
  const localConsumer = /\b(cafe|restaurant|bakery|salon|spa|gym|yoga|studio)\b/.test(ind);
  if (
    localConsumer &&
    platformSet.has("linkedin") &&
    !platformSet.has("instagram") &&
    !platformSet.has("facebook")
  ) {
    return {
      ok: false,
      hint: "Most cafes / local studios get traction on Instagram first — LinkedIn is heavier work for the same audience.",
    };
  }

  // B2B SaaS on Instagram-only = mismatch.
  const b2b = /\b(b2b|saas|enterprise|consulting|agency)\b/.test(ind);
  if (
    b2b &&
    platformSet.has("instagram") &&
    !platformSet.has("linkedin") &&
    platforms.length === 1
  ) {
    return {
      ok: false,
      hint: "B2B usually compounds faster on LinkedIn than Instagram — worth adding it to the mix.",
    };
  }

  return { ok: true };
}
