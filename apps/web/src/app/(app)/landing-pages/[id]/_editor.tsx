"use client";

import {
  ArrowLeft,
  ExternalLink,
  Loader2,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  type FormFieldType,
  type LandingPage,
  type LandingPageContent,
  type LandingPageStatus,
  type UpdateLandingPagePayload,
} from "@/lib/api";
import { cn } from "@/lib/utils";

export function Editor({ pageId }: { pageId: string }) {
  const router = useRouter();
  const [page, setPage] = useState<LandingPage | null>(null);
  const [content, setContent] = useState<LandingPageContent | null>(null);
  const [title, setTitle] = useState("");
  const [slug, setSlug] = useState("");
  const [status, setStatus] = useState<LandingPageStatus>("draft");
  const [redirectUrl, setRedirectUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    api.landingPages
      .get(pageId)
      .then((p) => {
        setPage(p);
        setContent(p.content);
        setTitle(p.title);
        setSlug(p.slug);
        setStatus(p.status);
        setRedirectUrl(p.redirect_url ?? "");
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load"),
      );
  }, [pageId]);

  const save = async (overrides: UpdateLandingPagePayload = {}) => {
    if (!page || !content) return;
    setSaving(true);
    setError(null);
    try {
      const payload: UpdateLandingPagePayload = {
        title,
        slug,
        content,
        status,
        redirect_url: redirectUrl.trim() || null,
        ...overrides,
      };
      const updated = await api.landingPages.update(page.id, payload);
      setPage(updated);
      setSavedAt(Date.now());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const publish = async () => {
    setStatus("published");
    await save({ status: "published" });
  };

  const unpublish = async () => {
    setStatus("draft");
    await save({ status: "draft" });
  };

  const archive = async () => {
    if (!page) return;
    if (!confirm("Archive this page? Public visitors will see a 404.")) return;
    try {
      await api.landingPages.update(page.id, { is_archived: true });
      router.push("/landing-pages" as never);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not archive");
    }
  };

  if (error && !page) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-destructive">
          {error}
        </CardContent>
      </Card>
    );
  }
  if (!page || !content) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading editor…
        </CardContent>
      </Card>
    );
  }

  const previewUrl = `/p/${page.slug}${
    status === "draft" ? `?preview=${page.preview_token}` : ""
  }`;

  const setField = <K extends keyof LandingPageContent>(
    key: K,
    value: LandingPageContent[K],
  ) => setContent({ ...content, [key]: value });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button asChild variant="ghost" size="sm">
            <Link href={"/landing-pages" as never}>
              <ArrowLeft className="h-4 w-4" />
              All pages
            </Link>
          </Button>
          <h1 className="text-lg font-semibold">{title || "Untitled page"}</h1>
          <span
            className={cn(
              "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
              status === "published"
                ? "bg-green-600/10 text-green-700 dark:text-green-400"
                : "bg-muted text-muted-foreground",
            )}
          >
            {status}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={previewUrl} target="_blank" rel="noreferrer">
              <ExternalLink className="h-3.5 w-3.5" />
              {status === "published" ? "View" : "Preview"}
            </a>
          </Button>
          {status === "published" ? (
            <Button variant="outline" size="sm" onClick={unpublish}>
              Unpublish
            </Button>
          ) : (
            <Button size="sm" onClick={publish}>
              Publish
            </Button>
          )}
          <Button onClick={() => save()} disabled={saving}>
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Save
          </Button>
        </div>
      </div>

      {savedAt && (
        <p className="text-xs text-muted-foreground">
          Saved {new Date(savedAt).toLocaleTimeString()}
        </p>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Meta + slug + redirect */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Meta</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="Internal title">
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </Field>
            <Field
              label="URL slug"
              hint={`Page will live at /p/${slug || "your-slug"}`}
            >
              <Input
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="summer-launch-2026"
              />
            </Field>
            <Field
              label="Post-submit redirect"
              hint="Optional. If set, visitors go here after submitting."
            >
              <Input
                value={redirectUrl}
                onChange={(e) => setRedirectUrl(e.target.value)}
                placeholder="https://yoursite.com/thanks"
              />
            </Field>
          </CardContent>
        </Card>

        {/* Hero */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Hero</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="Headline">
              <Input
                value={content.headline}
                onChange={(e) => setField("headline", e.target.value)}
              />
            </Field>
            <Field label="Subheadline">
              <Textarea
                rows={2}
                value={content.subheadline ?? ""}
                onChange={(e) =>
                  setField("subheadline", e.target.value || null)
                }
              />
            </Field>
            <Field label="CTA button text">
              <Input
                value={content.cta_text}
                onChange={(e) => setField("cta_text", e.target.value)}
              />
            </Field>
            <Field label="Privacy / small print">
              <Input
                value={content.privacy_blurb ?? ""}
                onChange={(e) =>
                  setField("privacy_blurb", e.target.value || null)
                }
                placeholder="No spam. Unsubscribe anytime."
              />
            </Field>
          </CardContent>
        </Card>

        {/* Benefits */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Benefits</CardTitle>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                setField("benefits", [
                  ...content.benefits,
                  { title: "", body: "" },
                ])
              }
              disabled={content.benefits.length >= 6}
            >
              <Plus className="h-3.5 w-3.5" /> Add
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {content.benefits.map((b, i) => (
              <RowEditor
                key={i}
                onRemove={() =>
                  setField(
                    "benefits",
                    content.benefits.filter((_, j) => j !== i),
                  )
                }
              >
                <Input
                  value={b.title}
                  onChange={(e) => {
                    const next = [...content.benefits];
                    next[i] = { ...b, title: e.target.value };
                    setField("benefits", next);
                  }}
                  placeholder="Save hours every week"
                />
                <Textarea
                  rows={2}
                  value={b.body}
                  onChange={(e) => {
                    const next = [...content.benefits];
                    next[i] = { ...b, body: e.target.value };
                    setField("benefits", next);
                  }}
                  placeholder="One sentence on the concrete benefit."
                />
              </RowEditor>
            ))}
          </CardContent>
        </Card>

        {/* Form fields */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Form fields</CardTitle>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                setField("form_fields", [
                  ...content.form_fields,
                  {
                    name: `field_${content.form_fields.length + 1}`,
                    label: "New field",
                    type: "text",
                    required: false,
                  },
                ])
              }
              disabled={content.form_fields.length >= 8}
            >
              <Plus className="h-3.5 w-3.5" /> Add
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {content.form_fields.map((f, i) => (
              <RowEditor
                key={i}
                onRemove={() =>
                  setField(
                    "form_fields",
                    content.form_fields.filter((_, j) => j !== i),
                  )
                }
              >
                <div className="grid gap-2 sm:grid-cols-2">
                  <Field label="Name (internal)">
                    <Input
                      value={f.name}
                      onChange={(e) => {
                        const next = [...content.form_fields];
                        next[i] = { ...f, name: e.target.value };
                        setField("form_fields", next);
                      }}
                    />
                  </Field>
                  <Field label="Label (visible)">
                    <Input
                      value={f.label}
                      onChange={(e) => {
                        const next = [...content.form_fields];
                        next[i] = { ...f, label: e.target.value };
                        setField("form_fields", next);
                      }}
                    />
                  </Field>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <Field label="Type">
                    <select
                      value={f.type}
                      onChange={(e) => {
                        const next = [...content.form_fields];
                        next[i] = {
                          ...f,
                          type: e.target.value as FormFieldType,
                        };
                        setField("form_fields", next);
                      }}
                      className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                    >
                      <option value="text">Text</option>
                      <option value="email">Email</option>
                      <option value="tel">Phone</option>
                      <option value="textarea">Textarea</option>
                    </select>
                  </Field>
                  <Field label="Required">
                    <label className="flex h-9 items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={f.required}
                        onChange={(e) => {
                          const next = [...content.form_fields];
                          next[i] = { ...f, required: e.target.checked };
                          setField("form_fields", next);
                        }}
                      />
                      <span>{f.required ? "Yes" : "No"}</span>
                    </label>
                  </Field>
                </div>
              </RowEditor>
            ))}
          </CardContent>
        </Card>

        {/* Social proof */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Social proof</CardTitle>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                setField("social_proof", [
                  ...content.social_proof,
                  { quote: "", author: "" },
                ])
              }
              disabled={content.social_proof.length >= 6}
            >
              <Plus className="h-3.5 w-3.5" /> Add
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {content.social_proof.map((s, i) => (
              <RowEditor
                key={i}
                onRemove={() =>
                  setField(
                    "social_proof",
                    content.social_proof.filter((_, j) => j !== i),
                  )
                }
              >
                <Textarea
                  rows={2}
                  value={s.quote}
                  onChange={(e) => {
                    const next = [...content.social_proof];
                    next[i] = { ...s, quote: e.target.value };
                    setField("social_proof", next);
                  }}
                  placeholder="Quote"
                />
                <div className="grid gap-2 sm:grid-cols-2">
                  <Input
                    value={s.author}
                    onChange={(e) => {
                      const next = [...content.social_proof];
                      next[i] = { ...s, author: e.target.value };
                      setField("social_proof", next);
                    }}
                    placeholder="Author"
                  />
                  <Input
                    value={s.role ?? ""}
                    onChange={(e) => {
                      const next = [...content.social_proof];
                      next[i] = { ...s, role: e.target.value || null };
                      setField("social_proof", next);
                    }}
                    placeholder="Role (optional)"
                  />
                </div>
              </RowEditor>
            ))}
          </CardContent>
        </Card>

        {/* FAQ */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">FAQ</CardTitle>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                setField("faq", [...content.faq, { q: "", a: "" }])
              }
              disabled={content.faq.length >= 10}
            >
              <Plus className="h-3.5 w-3.5" /> Add
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {content.faq.map((f, i) => (
              <RowEditor
                key={i}
                onRemove={() =>
                  setField(
                    "faq",
                    content.faq.filter((_, j) => j !== i),
                  )
                }
              >
                <Input
                  value={f.q}
                  onChange={(e) => {
                    const next = [...content.faq];
                    next[i] = { ...f, q: e.target.value };
                    setField("faq", next);
                  }}
                  placeholder="Question"
                />
                <Textarea
                  rows={2}
                  value={f.a}
                  onChange={(e) => {
                    const next = [...content.faq];
                    next[i] = { ...f, a: e.target.value };
                    setField("faq", next);
                  }}
                  placeholder="Answer"
                />
              </RowEditor>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm text-destructive">Danger zone</CardTitle>
        </CardHeader>
        <CardContent>
          <Button variant="destructive" size="sm" onClick={archive}>
            <Trash2 className="h-3.5 w-3.5" />
            Archive page
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {children}
    </div>
  );
}

function RowEditor({
  children,
  onRemove,
}: {
  children: React.ReactNode;
  onRemove: () => void;
}) {
  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      {children}
      <div className="flex justify-end">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={onRemove}
          className="text-muted-foreground"
        >
          <Trash2 className="h-3 w-3" />
          Remove
        </Button>
      </div>
    </div>
  );
}
