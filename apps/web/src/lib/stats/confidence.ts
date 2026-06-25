/**
 * Small-sample caveats for analytics surfaces.
 *
 * Why this exists: showing "75% conversion" off N=4 visits makes the
 * platform look like a toy. Founders trust honest numbers more than
 * impressive-looking ones. This helper lets every analytics surface
 * display rates with the right hedging based on sample size — no red
 * panic styling, just a quiet, muted caveat.
 *
 * Thresholds are deliberately conservative. Bump them when we have real
 * usage data on what feels right.
 */

export type SampleConfidence = "noise" | "early" | "directional" | "reliable";

export interface RateLabel {
  /** Headline display value, e.g. "75%", "3 of 4", or "—". */
  label: string;
  /** A short caveat to show beneath the number, or null when reliable. */
  caveat: string | null;
  /** Confidence bucket — callers use it to mute styling. */
  confidence: SampleConfidence;
  /** Whether the headline should render in muted color. */
  muted: boolean;
}

const THRESHOLDS = {
  // Below this many trials, don't even display a percentage — show fraction only.
  fractionFloor: 5,
  // Below this many trials, show the percentage but caveat heavily.
  earlySignal: 20,
  // Below this many trials, show the percentage with a soft caveat.
  directional: 100,
} as const;

/**
 * Format a rate (e.g. conversion = submissions/views) with the right
 * caveat based on the denominator. Pass the raw counts, not the rate —
 * we need `n` to make the call.
 */
export function formatRateWithCaveat(
  numerator: number,
  denominator: number,
  opts: { noun?: string } = {},
): RateLabel {
  const noun = opts.noun ?? "visits";

  if (denominator === 0) {
    return {
      label: "—",
      caveat: `No ${noun} yet.`,
      confidence: "noise",
      muted: true,
    };
  }

  const pct = (numerator / denominator) * 100;
  const pctText = pct >= 10 ? `${pct.toFixed(0)}%` : `${pct.toFixed(1)}%`;

  if (denominator < THRESHOLDS.fractionFloor) {
    // Too few trials — fraction is more honest than percentage.
    return {
      label: `${numerator} of ${denominator}`,
      caveat: `Early signal — too few ${noun} for a reliable rate yet.`,
      confidence: "noise",
      muted: true,
    };
  }

  if (denominator < THRESHOLDS.earlySignal) {
    return {
      label: pctText,
      caveat: `Early signal — small sample of ${denominator} ${noun}.`,
      confidence: "early",
      muted: true,
    };
  }

  if (denominator < THRESHOLDS.directional) {
    return {
      label: pctText,
      caveat: `Directional — based on ${denominator} ${noun}.`,
      confidence: "directional",
      muted: false,
    };
  }

  return {
    label: pctText,
    caveat: null,
    confidence: "reliable",
    muted: false,
  };
}

/**
 * Pure confidence bucket for a count without computing a rate.
 * Useful for "total leads = 3" type displays.
 */
export function sampleConfidence(n: number): SampleConfidence {
  if (n < THRESHOLDS.fractionFloor) return "noise";
  if (n < THRESHOLDS.earlySignal) return "early";
  if (n < THRESHOLDS.directional) return "directional";
  return "reliable";
}
