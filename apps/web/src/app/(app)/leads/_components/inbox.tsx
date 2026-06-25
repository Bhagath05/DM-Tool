"use client";

import { Download, Loader2, Plus, Search, Upload } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  api,
  type Lead,
  type LeadIntelligenceReport,
  type LeadPriorityItem,
  type LeadStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import { LeadDrawer } from "./lead-drawer";
import { LeadIntelligenceCard } from "./intelligence-card";
import { LeadRow } from "./lead-row";

const STATUS_FILTERS: { value: LeadStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "new", label: "New" },
  { value: "hot", label: "Hot" },
  { value: "warm", label: "Warm" },
  { value: "cold", label: "Cold" },
  { value: "archived", label: "Archived" },
];

const PAGE_SIZE = 50;

export function Inbox() {
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState<LeadStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [active, setActive] = useState<Lead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  // Phase 5 — keep the intelligence report in inbox state so each
  // <LeadRow> can show the matching priority badge, and the drawer
  // can render the opportunity block, without a second network call.
  const [intelligence, setIntelligence] =
    useState<LeadIntelligenceReport | null>(null);

  // Indexed by lead_id for O(1) lookup inside the list + drawer.
  const priorityByLead = useMemo<Map<string, LeadPriorityItem>>(() => {
    if (!intelligence) return new Map();
    return new Map(intelligence.priorities.map((p) => [p.lead_id, p]));
  }, [intelligence]);

  // Debounce the search input
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 250);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await api.leads.list({
        status: filter === "all" ? undefined : filter,
        search: debouncedSearch || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setLeads(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load leads");
    }
  }, [filter, debouncedSearch, offset]);

  useEffect(() => {
    load();
  }, [load]);

  // Reset to first page when filter or search changes
  useEffect(() => {
    setOffset(0);
  }, [filter, debouncedSearch]);

  const onLeadUpdated = (updated: Lead) => {
    setLeads((items) =>
      items ? items.map((l) => (l.id === updated.id ? updated : l)) : null,
    );
    if (active?.id === updated.id) setActive(updated);
  };

  const onLeadDeleted = (id: string) => {
    setLeads((items) => (items ? items.filter((l) => l.id !== id) : null));
    setTotal((t) => Math.max(0, t - 1));
    if (active?.id === id) setActive(null);
  };

  const exportHref = useMemo(
    () =>
      api.leads.exportUrl({
        status: filter === "all" ? undefined : filter,
      }),
    [filter],
  );

  const handleImport = async (file: File) => {
    setImportBusy(true);
    setError(null);
    try {
      const csv = await file.text();
      const result = await api.leads.importCsv(csv);
      await load();
      const detail =
        result.errors.length > 0
          ? ` ${result.errors.slice(0, 3).join(" ")}`
          : "";
      alert(`Imported ${result.inserted} leads.${detail}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImportBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Phase 5 — AI-ranked priorities sit above the toolbar. The
          inbox should answer "what should I do?" BEFORE listing rows
          (Constitution: analytics never lead). */}
      <LeadIntelligenceCard onReport={setIntelligence} />

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[260px] flex-1">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search email, name, company…"
            className="pl-8"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setFilter(f.value)}
              className={cn(
                "rounded-md border px-2.5 py-1 text-xs transition-colors",
                filter === f.value
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-input hover:bg-accent",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <Button asChild variant="outline" size="sm">
          <a href={exportHref} download>
            <Download className="h-3.5 w-3.5" />
            Export
          </a>
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={importBusy}
          onClick={() => {
            const input = document.createElement("input");
            input.type = "file";
            input.accept = ".csv,text/csv";
            input.onchange = () => {
              const file = input.files?.[0];
              if (file) void handleImport(file);
            };
            input.click();
          }}
        >
          {importBusy ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Upload className="h-3.5 w-3.5" />
          )}
          Import
        </Button>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          <Plus className="h-3.5 w-3.5" />
          Add lead
        </Button>
      </div>

      {addOpen && (
        <AddLeadForm
          onClose={() => setAddOpen(false)}
          onCreated={async (lead) => {
            setAddOpen(false);
            setLeads((items) => (items ? [lead, ...items] : [lead]));
            setTotal((t) => t + 1);
          }}
        />
      )}

      {/* List */}
      {error && (
        <Card>
          <CardContent className="pt-6 text-sm text-destructive">
            {error}
          </CardContent>
        </Card>
      )}

      {leads === null ? (
        <Card>
          <CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading leads…
          </CardContent>
        </Card>
      ) : leads.length === 0 ? (
        <Card>
          <CardContent className="space-y-1 pt-6 text-sm text-muted-foreground">
            <div className="font-medium text-foreground">No leads yet.</div>
            <p>
              Publish a lead page and share the URL — submissions will appear
              here.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="divide-y divide-border p-0">
            {leads.map((l) => (
              <LeadRow
                key={l.id}
                lead={l}
                onSelect={setActive}
                priority={priorityByLead.get(l.id) ?? null}
              />
            ))}
          </CardContent>
        </Card>
      )}

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <div>
            Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      {active && (
        <LeadDrawer
          lead={active}
          onClose={() => setActive(null)}
          onUpdated={onLeadUpdated}
          onDeleted={onLeadDeleted}
          priority={priorityByLead.get(active.id) ?? null}
        />
      )}
    </div>
  );
}

function AddLeadForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (lead: Lead) => void | Promise<void>;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [company, setCompany] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!email.trim()) {
      setError("Email is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const lead = await api.leads.create({
        email: email.trim(),
        name: name.trim() || null,
        phone: phone.trim() || null,
        company: company.trim() || null,
        message: message.trim() || null,
      });
      await onCreated(lead);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't add lead");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardContent className="space-y-3 pt-6">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium">Add lead manually</div>
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
        </div>
        <Input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email *"
          type="email"
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name"
          />
          <Input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="Phone"
          />
        </div>
        <Input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          placeholder="Company"
        />
        <Input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Message / notes"
        />
        {error && <p className="text-xs text-destructive">{error}</p>}
        <Button size="sm" onClick={submit} disabled={busy}>
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
          Save lead
        </Button>
      </CardContent>
    </Card>
  );
}
