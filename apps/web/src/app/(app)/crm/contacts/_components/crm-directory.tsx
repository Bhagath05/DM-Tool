"use client";

/**
 * Phase 6.5 Slice 2 — CRM Contacts & Companies directory.
 *
 * Tabbed directory over the live /crm entities API: search, quick-create, and a
 * detail modal per record showing fields, relationships (associated contacts /
 * deals), the activity timeline, grounded AI summary, and duplicate → merge.
 * Design system reused throughout; responsive.
 */

import { Building2, Merge, Plus, Search, Sparkles, User } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { Surface } from "@/components/ui/surface";
import {
  api,
  type CrmActivity,
  type CrmCompany,
  type CrmContact,
  type CrmDuplicate,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type Tab = "companies" | "contacts";

function healthTone(score: number | null): "good" | "watch" | "bad" | "neutral" {
  if (score == null) return "neutral";
  return score >= 70 ? "good" : score >= 45 ? "watch" : "bad";
}

// ---------------------------------------------------------------- detail modal
function DetailModal({
  kind,
  id,
  onClose,
  onChanged,
}: {
  kind: Tab;
  id: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const isCompany = kind === "companies";
  const [detail, setDetail] = useState<{
    company?: CrmCompany;
    contact?: CrmContact;
    contacts?: CrmContact[];
    deals?: { id: string; title: string; value: number; status: string }[];
  } | null>(null);
  const [activities, setActivities] = useState<CrmActivity[]>([]);
  const [dupes, setDupes] = useState<CrmDuplicate[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (isCompany) {
      const [d, acts, dp] = await Promise.all([
        api.crm.company(id),
        api.crm.companyActivities(id),
        api.crm.companyDuplicates(id).then((r) => r.items).catch(() => []),
      ]);
      setDetail({ company: d.company, contacts: d.contacts, deals: d.deals });
      setActivities(acts);
      setDupes(dp);
    } else {
      const [d, acts, dp] = await Promise.all([
        api.crm.contact(id),
        api.crm.contactActivities(id),
        api.crm.contactDuplicates(id).then((r) => r.items).catch(() => []),
      ]);
      setDetail({ contact: d.contact, company: d.company ?? undefined, deals: d.deals });
      setActivities(acts);
      setDupes(dp);
    }
  }, [id, isCompany]);

  useEffect(() => {
    void load();
  }, [load]);

  const entity = isCompany ? detail?.company : detail?.contact;

  const runSummary = async () => {
    setBusy(true);
    try {
      if (isCompany) await api.crm.companySummary(id);
      else await api.crm.contactSummary(id);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const runHealth = async () => {
    setBusy(true);
    try {
      await api.crm.companyHealth(id);
      await load();
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const merge = async (dupId: string) => {
    if (!confirm("Merge this duplicate into the current record? This cannot be undone.")) return;
    setBusy(true);
    try {
      if (isCompany) await api.crm.mergeCompany(id, dupId);
      else await api.crm.mergeContact(id, dupId);
      await load();
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const summary = (entity as CrmCompany | CrmContact | undefined)?.ai_summary ?? null;

  return (
    <Modal
      open
      onOpenChange={(o) => !o && onClose()}
      title={entity?.name ?? "Loading…"}
      description={isCompany ? (detail?.company?.industry ?? undefined) : (detail?.contact?.title ?? undefined)}
      className="max-w-3xl"
      data-testid="crm-detail-modal"
    >
      {!entity ? (
        <div className="p-4"><Skeleton className="h-40 w-full" /></div>
      ) : (
        <div className="space-y-4 p-4">
          {/* Header actions */}
          <div className="flex flex-wrap items-center gap-2">
            {isCompany && (
              <StatusPill tone={healthTone(detail?.company?.health_score ?? null)} size="sm">
                Health {detail?.company?.health_score ?? "—"}
              </StatusPill>
            )}
            {isCompany && (
              <Button size="sm" variant="outline" onClick={() => void runHealth()} disabled={busy}>
                Recompute health
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => void runSummary()} disabled={busy}>
              <Sparkles className="h-4 w-4" /> AI summary
            </Button>
          </div>

          {/* Fields */}
          <div className="grid gap-2 text-sm sm:grid-cols-2">
            {isCompany ? (
              <>
                {detail?.company?.website && <Field label="Website" value={detail.company.website} />}
                {detail?.company?.employees != null && <Field label="Employees" value={String(detail.company.employees)} />}
                {detail?.company?.annual_revenue != null && <Field label="Revenue" value={String(detail.company.annual_revenue)} />}
                {detail?.company?.timezone && <Field label="Timezone" value={detail.company.timezone} />}
                {(detail?.company?.tech_stack.length ?? 0) > 0 && (
                  <Field label="Tech stack" value={detail!.company!.tech_stack.join(", ")} />
                )}
              </>
            ) : (
              <>
                {detail?.contact?.email && <Field label="Email" value={detail.contact.email} />}
                {detail?.contact?.phone && <Field label="Phone" value={detail.contact.phone} />}
                {detail?.contact?.linkedin && <Field label="LinkedIn" value={detail.contact.linkedin} />}
                {detail?.company && <Field label="Company" value={detail.company.name} />}
              </>
            )}
          </div>

          {/* AI summary */}
          {summary && (
            <Surface state="ai" padding="compact" className="space-y-1">
              <p className="text-sm">{summary.summary}</p>
              {(summary.talking_points ?? summary.opportunities ?? []).length > 0 && (
                <ul className="list-inside list-disc text-xs text-muted-foreground">
                  {(summary.talking_points ?? summary.opportunities ?? []).map((t, i) => <li key={i}>{t}</li>)}
                </ul>
              )}
              <StatusPill tone="good" size="sm">{summary.confidence}% confidence</StatusPill>
            </Surface>
          )}

          {/* Duplicates → merge */}
          {dupes.length > 0 && (
            <Surface state="watch" padding="compact" className="space-y-1">
              <p className="text-xs font-medium">Possible duplicates</p>
              {dupes.map((d) => (
                <div key={d.id} className="flex items-center justify-between text-sm">
                  <span>{d.name} <span className="text-xs text-muted-foreground">({d.reason})</span></span>
                  <Button size="sm" variant="outline" onClick={() => void merge(d.id)} disabled={busy}>
                    <Merge className="h-3.5 w-3.5" /> Merge in
                  </Button>
                </div>
              ))}
            </Surface>
          )}

          {/* Relationships */}
          <div className="grid gap-3 sm:grid-cols-2">
            {isCompany && (
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">Contacts ({detail?.contacts?.length ?? 0})</p>
                {(detail?.contacts ?? []).map((c) => (
                  <p key={c.id} className="text-sm">{c.name}{c.title ? ` · ${c.title}` : ""}</p>
                ))}
                {(detail?.contacts?.length ?? 0) === 0 && <p className="text-xs text-muted-foreground">None</p>}
              </div>
            )}
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Deals ({detail?.deals?.length ?? 0})</p>
              {(detail?.deals ?? []).map((d) => (
                <p key={d.id} className="text-sm">
                  {d.title} <StatusPill tone={d.status === "won" ? "good" : d.status === "lost" ? "bad" : "neutral"} size="sm">{d.status}</StatusPill>
                </p>
              ))}
              {(detail?.deals?.length ?? 0) === 0 && <p className="text-xs text-muted-foreground">None</p>}
            </div>
          </div>

          {/* Timeline */}
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Timeline</p>
            {activities.length === 0 ? (
              <p className="text-xs text-muted-foreground">No activity logged.</p>
            ) : (
              <ul className="space-y-1">
                {activities.map((a) => (
                  <li key={a.id} className="flex items-center gap-2 text-xs">
                    <StatusPill tone="neutral" size="sm">{a.kind}</StatusPill>
                    <span>{a.subject || a.body?.slice(0, 60) || "—"}</span>
                    <span className="ml-auto text-muted-foreground">{new Date(a.occurred_at).toLocaleDateString()}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="truncate">{value}</p>
    </div>
  );
}

// ---------------------------------------------------------------- directory
export function CrmDirectory() {
  const [tab, setTab] = useState<Tab>("companies");
  const [search, setSearch] = useState("");
  const [companies, setCompanies] = useState<CrmCompany[]>([]);
  const [contacts, setContacts] = useState<CrmContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === "companies") {
        setCompanies((await api.crm.companies({ q: search || undefined })).items);
      } else {
        setContacts((await api.crm.contacts({ q: search || undefined })).items);
      }
    } finally {
      setLoading(false);
    }
  }, [tab, search]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 200);
    return () => clearTimeout(t);
  }, [load]);

  const add = async () => {
    if (!newName.trim()) return;
    if (tab === "companies") await api.crm.createCompany({ name: newName.trim() });
    else await api.crm.createContact({ name: newName.trim() });
    setNewName("");
    void load();
  };

  const rows = tab === "companies" ? companies : contacts;

  return (
    <div className="space-y-4" data-testid="crm-directory">
      <SectionHeading
        eyebrow="CRM"
        heading="Contacts & Companies"
        description="Your relationship graph — search, dedupe, merge, and see every deal and touchpoint."
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-md border border-border p-0.5">
          {(["companies", "contacts"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "flex items-center gap-1.5 rounded px-3 py-1 text-sm capitalize",
                tab === t ? "bg-primary text-primary-foreground" : "text-muted-foreground",
              )}
              data-testid={`crm-tab-${t}`}
            >
              {t === "companies" ? <Building2 className="h-4 w-4" /> : <User className="h-4 w-4" />}
              {t}
            </button>
          ))}
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`Search ${tab}…`}
            className="h-9 w-56 pl-8"
            data-testid="crm-search"
          />
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={tab === "companies" ? "New company name…" : "New contact name…"}
            className="h-9 w-48"
          />
          <Button size="sm" onClick={() => void add()} disabled={!newName.trim()}>
            <Plus className="h-4 w-4" /> Add
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={tab === "companies" ? Building2 : User}
          title={`No ${tab} yet`}
          description="Add one above, or they'll appear here as your CRM grows."
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {tab === "companies"
            ? companies.map((c) => (
                <button key={c.id} onClick={() => setOpenId(c.id)} className="text-left" data-testid="crm-row">
                  <Surface padding="compact" className="h-full space-y-1 hover:border-primary">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{c.name}</span>
                      {c.health_score != null && (
                        <StatusPill tone={healthTone(c.health_score)} size="sm">{c.health_score}</StatusPill>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">{c.industry || c.domain || "—"}</p>
                  </Surface>
                </button>
              ))
            : contacts.map((c) => (
                <button key={c.id} onClick={() => setOpenId(c.id)} className="text-left" data-testid="crm-row">
                  <Surface padding="compact" className="h-full space-y-1 hover:border-primary">
                    <span className="font-medium">{c.name}</span>
                    <p className="text-xs text-muted-foreground">{c.title || c.email || "—"}</p>
                  </Surface>
                </button>
              ))}
        </div>
      )}

      {openId && (
        <DetailModal
          kind={tab}
          id={openId}
          onClose={() => setOpenId(null)}
          onChanged={() => void load()}
        />
      )}
    </div>
  );
}
