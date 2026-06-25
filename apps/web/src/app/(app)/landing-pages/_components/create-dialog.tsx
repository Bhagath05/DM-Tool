"use client";

import { Loader2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, type CreateLandingPagePayload } from "@/lib/api";

const DEFAULT_CONTENT: CreateLandingPagePayload["content"] = {
  headline: "Get our free guide",
  subheadline: "The 10-minute checklist successful founders use every week.",
  benefits: [
    {
      title: "Save hours every week",
      body: "Skip the boilerplate — start from a tested playbook.",
    },
    {
      title: "Battle-tested with 1000+ teams",
      body: "Proven across launches, relaunches and refreshes.",
    },
  ],
  cta_text: "Send me the guide",
  form_fields: [
    {
      name: "email",
      label: "Work email",
      type: "email",
      required: true,
      placeholder: "you@company.com",
    },
    {
      name: "name",
      label: "Name",
      type: "text",
      required: false,
      placeholder: "Jane Doe",
    },
  ],
  social_proof: [],
  faq: [],
  privacy_blurb: "No spam. Unsubscribe anytime.",
};

export function CreateDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [headline, setHeadline] = useState("");
  const [subheadline, setSubheadline] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const content = {
        ...DEFAULT_CONTENT,
        headline: headline.trim() || DEFAULT_CONTENT.headline,
        subheadline: subheadline.trim() || DEFAULT_CONTENT.subheadline,
      };
      const created = await api.landingPages.create({
        title: title.trim(),
        content,
      });
      onCreated();
      router.push(`/landing-pages/${created.id}` as never);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create page");
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-border bg-card shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h3 className="text-sm font-semibold">New lead page</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={onSubmit} className="space-y-4 p-5">
          <div className="space-y-1.5">
            <Label htmlFor="lp-title">Internal title</Label>
            <p className="text-xs text-muted-foreground">
              Only you see this — not visitors.
            </p>
            <Input
              id="lp-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Summer 2026 launch waitlist"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="lp-headline">Headline (visible on the page)</Label>
            <Input
              id="lp-headline"
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              placeholder="Get our free guide"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="lp-sub">Subheadline (optional)</Label>
            <Textarea
              id="lp-sub"
              rows={2}
              value={subheadline}
              onChange={(e) => setSubheadline(e.target.value)}
              placeholder="One short sentence on the value exchange."
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || !title.trim()}>
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                "Create & edit"
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
