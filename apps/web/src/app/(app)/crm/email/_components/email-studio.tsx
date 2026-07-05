"use client";

/**
 * Phase 6.5 Slice 4 — CRM Email Studio.
 *
 * Templates (manage + edit + variable preview + version count), sequences
 * (build + activate + run), and a tracking dashboard (real open/click/reply
 * rates), over the live /crm/email API. Sending uses the record-only provider
 * until real credentials are configured — the UI is honest about that.
 * Design system reused; responsive.
 */

import { FileText, Mail, Play, Plus, Send, Workflow } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { Surface } from "@/components/ui/surface";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  type CrmEmailCategory,
  type CrmEmailSequence,
  type CrmEmailStats,
  type CrmEmailTemplate,
} from "@/lib/api";
import { humanize, pct } from "@/lib/crm-format";
import { cn } from "@/lib/utils";

type Tab = "templates" | "sequences" | "tracking";

const CATEGORIES: CrmEmailCategory[] = [
  "welcome", "follow_up", "proposal", "reminder", "thank_you", "meeting", "renewal", "custom",
];

// ---------------------------------------------------------------- editor modal
function TemplateEditor({
  template,
  onClose,
  onSaved,
}: {
  template: CrmEmailTemplate | null; // null = create
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(template?.name ?? "");
  const [category, setCategory] = useState<CrmEmailCategory>(template?.category ?? "custom");
  const [subject, setSubject] = useState(template?.subject ?? "");
  const [body, setBody] = useState(template?.body ?? "Hi {{contact_first_name}},\n\n");
  const [preview, setPreview] = useState<{ subject: string; body: string; unresolved: string[] } | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!name.trim() || !subject.trim() || !body.trim()) return;
    setBusy(true);
    try {
      if (template) {
        await api.crm.updateEmailTemplate(template.id, { name, category, subject, body });
      } else {
        await api.crm.createEmailTemplate({ name, category, subject, body });
      }
      onSaved();
      onClose();
    } finally {
      setBusy(false);
    }
  };

  const runPreview = async () => {
    if (!template) return;
    setPreview(await api.crm.renderEmailTemplate(template.id, { contact_first_name: "Sam", company: "Acme Co" }));
  };

  return (
    <Modal open onOpenChange={(o) => !o && onClose()}
      title={template ? "Edit template" : "New template"}
      description={template ? `Version ${template.current_version}` : undefined}
      className="max-w-2xl" data-testid="template-editor">
      <div className="space-y-3 p-4">
        <div className="flex gap-2">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Template name" />
          <select value={category} onChange={(e) => setCategory(e.target.value as CrmEmailCategory)}
            className="h-9 rounded-md border border-input bg-background px-2 text-sm">
            {CATEGORIES.map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
          </select>
        </div>
        <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Subject — use {{variables}}" />
        <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={8}
          placeholder="Body — {{contact_first_name}}, {{company}}…" data-testid="template-body" />
        <p className="text-xs text-muted-foreground">
          Use <code>{"{{variable}}"}</code> placeholders — e.g. contact_first_name, contact_name, company.
        </p>

        <div className="flex gap-2">
          <Button size="sm" onClick={() => void save()} disabled={busy}>Save</Button>
          {template && (
            <Button size="sm" variant="outline" onClick={() => void runPreview()}>Preview</Button>
          )}
        </div>

        {preview && (
          <Surface padding="compact" className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Preview (sample values)</p>
            <p className="text-sm font-medium">{preview.subject}</p>
            <p className="whitespace-pre-wrap text-sm">{preview.body}</p>
            {preview.unresolved.length > 0 && (
              <p className="text-xs text-watch">Unfilled: {preview.unresolved.join(", ")}</p>
            )}
          </Surface>
        )}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- main
export function EmailStudio() {
  const [tab, setTab] = useState<Tab>("templates");
  const [templates, setTemplates] = useState<CrmEmailTemplate[]>([]);
  const [sequences, setSequences] = useState<CrmEmailSequence[]>([]);
  const [stats, setStats] = useState<CrmEmailStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<CrmEmailTemplate | null | "new">(null);
  const [newSeq, setNewSeq] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === "templates") setTemplates((await api.crm.emailTemplates()).items);
      else if (tab === "sequences") setSequences(await api.crm.emailSequences());
      else setStats(await api.crm.emailStats());
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    void load();
  }, [load]);

  const addSequence = async () => {
    if (!newSeq.trim()) return;
    await api.crm.createEmailSequence({ name: newSeq.trim(), steps: [] });
    setNewSeq("");
    void load();
  };

  const toggleSequence = async (s: CrmEmailSequence) => {
    await api.crm.updateEmailSequence(s.id, { status: s.status === "active" ? "draft" : "active" });
    void load();
  };

  return (
    <div className="space-y-4" data-testid="email-studio">
      <SectionHeading
        eyebrow="CRM"
        heading="Email"
        description="Templates, multi-step sequences, and tracking — every email logs to the contact's timeline."
      />

      <div className="inline-flex rounded-md border border-border p-0.5">
        {([["templates", FileText], ["sequences", Workflow], ["tracking", Mail]] as [Tab, typeof Mail][]).map(([t, Icon]) => (
          <button key={t} onClick={() => setTab(t)}
            className={cn("flex items-center gap-1.5 rounded px-3 py-1 text-sm capitalize",
              tab === t ? "bg-primary text-primary-foreground" : "text-muted-foreground")}
            data-testid={`email-tab-${t}`}>
            <Icon className="h-4 w-4" /> {t}
          </button>
        ))}
      </div>

      {loading ? (
        <Skeleton className="h-48 w-full" />
      ) : tab === "templates" ? (
        <div className="space-y-3">
          <Button size="sm" onClick={() => setEditing("new")} data-testid="new-template">
            <Plus className="h-4 w-4" /> New template
          </Button>
          {templates.length === 0 ? (
            <EmptyState icon={FileText} title="No templates yet"
              description="Create reusable emails with {{variables}} for welcome, follow-up, proposal, and more." />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {templates.map((t) => (
                <button key={t.id} onClick={() => setEditing(t)} className="text-left" data-testid="template-card">
                  <Surface padding="compact" className="h-full space-y-1 hover:border-primary">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{t.name}</span>
                      <StatusPill tone="neutral" size="sm">{humanize(t.category)}</StatusPill>
                    </div>
                    <p className="truncate text-xs text-muted-foreground">{t.subject}</p>
                    <p className="text-xs text-muted-foreground">v{t.current_version}{t.is_active ? "" : " · inactive"}</p>
                  </Surface>
                </button>
              ))}
            </div>
          )}
        </div>
      ) : tab === "sequences" ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Input value={newSeq} onChange={(e) => setNewSeq(e.target.value)} placeholder="New sequence name…" className="w-56" />
            <Button size="sm" onClick={() => void addSequence()} disabled={!newSeq.trim()}>
              <Plus className="h-4 w-4" /> Add
            </Button>
            <Button size="sm" variant="outline" onClick={() => void api.crm.runSequences().then(() => load())}>
              <Play className="h-4 w-4" /> Run due
            </Button>
          </div>
          {sequences.length === 0 ? (
            <EmptyState icon={Workflow} title="No sequences yet"
              description="Build multi-step email sequences with delays and stop-on-reply conditions." />
          ) : (
            <div className="space-y-2">
              {sequences.map((s) => (
                <Surface key={s.id} padding="compact" className="flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{s.name}</p>
                    <p className="text-xs text-muted-foreground">{s.steps.length} step{s.steps.length === 1 ? "" : "s"}</p>
                  </div>
                  <StatusPill tone={s.status === "active" ? "good" : "neutral"} size="sm">{s.status}</StatusPill>
                  <Button size="sm" variant="outline" onClick={() => void toggleSequence(s)}>
                    {s.status === "active" ? "Pause" : "Activate"}
                  </Button>
                </Surface>
              ))}
            </div>
          )}
        </div>
      ) : stats ? (
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {([
            ["Sent", String(stats.sent)],
            ["Open rate", pct(stats.open_rate)],
            ["Click rate", pct(stats.click_rate)],
            ["Reply rate", pct(stats.reply_rate)],
            ["Delivered", String(stats.delivered)],
            ["Bounced", String(stats.bounced)],
            ["Unsubscribed", String(stats.unsubscribed)],
            ["Bounce rate", pct(stats.bounce_rate)],
          ] as [string, string][]).map(([label, val]) => (
            <Surface key={label} padding="compact" className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">{label}</span>
              <span className="text-xl font-semibold">{val}</span>
            </Surface>
          ))}
          <Surface padding="compact" className="col-span-full flex items-center gap-2 text-xs text-muted-foreground">
            <Send className="h-3 w-3" />
            Tracking reflects real events only — emails send once an email provider is configured.
          </Surface>
        </div>
      ) : null}

      {editing !== null && (
        <TemplateEditor
          template={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => void load()}
        />
      )}
    </div>
  );
}
