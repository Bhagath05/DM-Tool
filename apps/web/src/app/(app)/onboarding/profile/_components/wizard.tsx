"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { FormProvider, useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import {
  STEP_FIELDS,
  STEP_LABELS,
  STEP_SCHEMAS,
  onboardingFormSchema,
  toSubmitPayload,
  type OnboardingFormValues,
} from "@/lib/onboarding-schema";

import { Stepper } from "./stepper";
import {
  StepAudience,
  StepBrandTone,
  StepBusiness,
  StepCompetitors,
  StepGoals,
  StepPlatforms,
  StepReview,
} from "./steps";

const STORAGE_KEY = "aicmo:onboarding-draft:v1";
const STEP_COUNT = STEP_LABELS.length;

const STEP_COMPONENTS = [
  StepBusiness,
  StepAudience,
  StepCompetitors,
  StepGoals,
  StepBrandTone,
  StepPlatforms,
  StepReview,
];

const DEFAULTS: OnboardingFormValues = {
  business_name: "",
  website: undefined,
  industry: "",
  target_audience: "",
  competitors_text: "",
  goals_text: "",
  brand_tone: "Professional",
  preferred_platforms: [],
};

export function OnboardingWizard() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<OnboardingFormValues>({
    resolver: zodResolver(onboardingFormSchema),
    defaultValues: DEFAULTS,
    mode: "onTouched",
  });

  // Restore draft once on mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw);
      form.reset({ ...DEFAULTS, ...parsed });
    } catch {
      // Drop a corrupted draft silently.
      window.localStorage.removeItem(STORAGE_KEY);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist on every change.
  useEffect(() => {
    const sub = form.watch((value) => {
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
      } catch {
        /* quota — ignore */
      }
    });
    return () => sub.unsubscribe();
  }, [form]);

  const Current = STEP_COMPONENTS[step];

  const onNext = async () => {
    setSubmitError(null);
    const schema = STEP_SCHEMAS[step];
    const values = form.getValues();
    const parsed = schema.safeParse(values);
    if (!parsed.success) {
      // Trigger RHF validation on the fields owned by this step so errors render.
      await form.trigger(STEP_FIELDS[step] as never);
      return;
    }
    if (step < STEP_COUNT - 1) {
      setStep((s) => s + 1);
      return;
    }
    await onSubmit();
  };

  const onBack = () => {
    setSubmitError(null);
    setStep((s) => Math.max(0, s - 1));
  };

  const onSubmit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const payload = toSubmitPayload(form.getValues());
      await api.business.submit(payload);
      window.localStorage.removeItem(STORAGE_KEY);
      router.replace("/dashboard");
      router.refresh();
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Submission failed");
      setSubmitting(false);
    }
  };

  const isLast = step === STEP_COUNT - 1;

  return (
    <FormProvider {...form}>
      <div className="space-y-6">
        <Stepper current={step} labels={STEP_LABELS} />
        <Card>
          <CardContent className="space-y-6 pt-6">
            <Current />
          </CardContent>
        </Card>
        {submitError && (
          <p className="text-sm text-destructive">{submitError}</p>
        )}
        <div className="flex items-center justify-between">
          <Button
            variant="ghost"
            onClick={onBack}
            disabled={step === 0 || submitting}
            type="button"
          >
            <ChevronLeft className="h-4 w-4" />
            Back
          </Button>
          <div className="text-xs text-muted-foreground">
            Step {step + 1} of {STEP_COUNT}
          </div>
          <Button
            onClick={onNext}
            disabled={submitting}
            type="button"
            className="min-w-[120px]"
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : isLast ? (
              "Submit"
            ) : (
              <>
                Next
                <ChevronRight className="h-4 w-4" />
              </>
            )}
          </Button>
        </div>
      </div>
    </FormProvider>
  );
}
