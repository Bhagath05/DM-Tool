import { z } from "zod";

export const BRAND_TONES = [
  "Professional",
  "Casual",
  "Playful",
  "Bold",
  "Inspirational",
  "Authoritative",
  "Warm",
] as const;

export const PLATFORMS = [
  "Instagram",
  "TikTok",
  "X (Twitter)",
  "LinkedIn",
  "YouTube",
  "Facebook",
  "Pinterest",
  "Threads",
  "Reddit",
  "Email",
] as const;

const trimmedNonEmpty = (s: string) => s.trim().length > 0;
const linesToList = (input: string): string[] =>
  input
    .split("\n")
    .map((s) => s.trim())
    .filter(trimmedNonEmpty);

export const stepBusinessSchema = z.object({
  business_name: z.string().min(2, "Business name is required").max(255),
  website: z
    .string()
    .trim()
    .url("Must be a valid URL (https://…)")
    .max(512)
    .optional()
    .or(z.literal("").transform(() => undefined)),
  industry: z.string().min(2, "Industry is required").max(128),
});

export const stepAudienceSchema = z.object({
  target_audience: z
    .string()
    .trim()
    .min(10, "Describe the audience in at least a sentence")
    .max(2000),
});

export const stepCompetitorsSchema = z.object({
  competitors_text: z.string().optional().default(""),
});

export const stepGoalsSchema = z.object({
  goals_text: z
    .string()
    .refine((s) => linesToList(s).length >= 1, "Add at least one goal"),
});

export const stepBrandToneSchema = z.object({
  brand_tone: z.enum(BRAND_TONES, {
    errorMap: () => ({ message: "Pick a brand tone" }),
  }),
});

export const stepPlatformsSchema = z.object({
  preferred_platforms: z
    .array(z.string())
    .min(1, "Pick at least one platform")
    .max(15),
});

export const onboardingFormSchema = stepBusinessSchema
  .merge(stepAudienceSchema)
  .merge(stepCompetitorsSchema)
  .merge(stepGoalsSchema)
  .merge(stepBrandToneSchema)
  .merge(stepPlatformsSchema);

export type OnboardingFormValues = z.infer<typeof onboardingFormSchema>;

export interface OnboardingSubmitPayload {
  business_name: string;
  website?: string;
  industry: string;
  target_audience: string;
  competitors: string[];
  goals: string[];
  brand_tone: string;
  preferred_platforms: string[];
}

export function toSubmitPayload(
  values: OnboardingFormValues,
): OnboardingSubmitPayload {
  return {
    business_name: values.business_name.trim(),
    website: values.website || undefined,
    industry: values.industry.trim(),
    target_audience: values.target_audience.trim(),
    competitors: linesToList(values.competitors_text ?? ""),
    goals: linesToList(values.goals_text),
    brand_tone: values.brand_tone,
    preferred_platforms: values.preferred_platforms,
  };
}

export const STEP_SCHEMAS = [
  stepBusinessSchema,
  stepAudienceSchema,
  stepCompetitorsSchema,
  stepGoalsSchema,
  stepBrandToneSchema,
  stepPlatformsSchema,
  z.object({}),
] as const;

export const STEP_FIELDS: ReadonlyArray<ReadonlyArray<keyof OnboardingFormValues>> = [
  ["business_name", "website", "industry"],
  ["target_audience"],
  ["competitors_text"],
  ["goals_text"],
  ["brand_tone"],
  ["preferred_platforms"],
  [],
] as const;

export const STEP_LABELS = [
  "Business",
  "Audience",
  "Competitors",
  "Goals",
  "Brand tone",
  "Platforms",
  "Review",
] as const;
