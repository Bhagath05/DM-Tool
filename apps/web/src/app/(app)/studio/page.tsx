/**
 * Creative Studio (CS3) — outcome → editable campaign, flag-gated.
 *
 * The user states a business outcome ("I need 50 qualified cybersecurity
 * leads"); the Strategy Engine plans it and the composers produce a set of
 * editable creatives (poster / carousel / ad / reel). Each result is a real
 * editable design (read-only preview here; the canvas lands in CS5). Dark
 * unless NEXT_PUBLIC_STUDIO_ENABLED === "true".
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { DesignViewer } from "@/components/studio/design-viewer";
import { EditorShell } from "@/components/studio/editor/editor-shell";
import { NlEditPanel } from "@/components/studio/nl-edit-panel";
import { ObjectStorageNotice } from "@/components/studio/object-storage-notice";
import { RevisionHistory } from "@/components/studio/revision-history";
import { VideoPanel } from "@/components/studio/video-panel";
import { Surface } from "@/components/ui/surface";
import { api } from "@/lib/api";
import { isStudioEnabled } from "@/lib/studio-config";
import type {
  CampaignStrategyOut,
  DesignDoc,
  DesignResponse,
  DesignSummary,
  ObjectiveKind,
  RevisionSummary,
} from "@/lib/studio-types";

export default function StudioPage() {
  const enabled = isStudioEnabled();
  const [kinds, setKinds] = useState<ObjectiveKind[]>([]);
  const [kind, setKind] = useState("get_leads");
  const [goal, setGoal] = useState("");
  const [building, setBuilding] = useState(false);
  const [strategy, setStrategy] = useState<CampaignStrategyOut | null>(null);

  const [designs, setDesigns] = useState<DesignSummary[]>([]);
  const [selected, setSelected] = useState<DesignResponse | null>(null);
  const [revisions, setRevisions] = useState<RevisionSummary[]>([]);
  const [previewDoc, setPreviewDoc] = useState<DesignDoc | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const open = useCallback(async (id: string) => {
    setError(null);
    setPreviewDoc(null);
    try {
      const [design, revs] = await Promise.all([
        api.studio.getDesign(id),
        api.studio.listRevisions(id),
      ]);
      setSelected(design);
      setRevisions(revs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to open design.");
    }
  }, []);

  const refreshDesigns = useCallback(
    async (openFirst = false) => {
      const items = await api.studio.listDesigns();
      setDesigns(items);
      if (openFirst && items.length > 0) void open(items[0].id);
      return items;
    },
    [open],
  );

  useEffect(() => {
    if (!enabled) return;
    setLoading(true);
    Promise.all([api.growth.objectiveKinds().catch(() => []), refreshDesigns(true)])
      .then(([k]) => setKinds(k))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load studio."))
      .finally(() => setLoading(false));
  }, [enabled, refreshDesigns]);

  const generate = useCallback(async () => {
    if (!goal.trim()) return;
    setBuilding(true);
    setError(null);
    setStrategy(null);
    try {
      const objective = await api.growth.createObjective({
        objective_kind: kind,
        statement: goal.trim(),
      });
      const result = await api.growth.buildCampaign(objective.id);
      setStrategy(result.strategy);
      await refreshDesigns();
      if (result.assets.length > 0) void open(result.assets[0].design_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to build the campaign.");
    } finally {
      setBuilding(false);
    }
  }, [goal, kind, open, refreshDesigns]);

  if (!enabled) {
    return (
      <div className="mx-auto max-w-2xl p-8">
        <Surface className="p-8 text-center">
          <h1 className="text-lg font-semibold">Creative Studio</h1>
          <p className="mt-2 text-sm text-[var(--muted-foreground,#64748b)]">
            Tell us your goal — &quot;I need 50 qualified leads&quot; — and the
            Studio will plan the strategy and produce editable posters, carousels,
            ads, and reels. Coming soon.
          </p>
        </Surface>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl p-6">
      <header className="mb-6">
        <h1 className="text-xl font-semibold">Creative Studio</h1>
        <p className="text-sm text-[var(--muted-foreground,#64748b)]">
          State an outcome. Get a strategy and a set of editable creatives.
        </p>
      </header>

      <ObjectStorageNotice />

      {/* Campaign intake — the priority flow */}
      <Surface className="mb-6 p-4">
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground,#64748b)]">
          What outcome do you want?
        </label>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="I need 50 qualified cybersecurity leads"
            className="flex-1 rounded-md border border-[var(--border,#e2e8f0)] px-3 py-2 text-sm"
            onKeyDown={(e) => {
              if (e.key === "Enter") void generate();
            }}
          />
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className="rounded-md border border-[var(--border,#e2e8f0)] px-3 py-2 text-sm"
            aria-label="Objective type"
          >
            {(kinds.length > 0
              ? kinds
              : [{ slug: "get_leads", display_name: "Get Leads" } as ObjectiveKind]
            ).map((k) => (
              <option key={k.slug} value={k.slug}>
                {k.display_name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void generate()}
            disabled={building || !goal.trim()}
            className="rounded-md bg-[var(--primary,#2563eb)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {building ? "Generating…" : "Generate campaign"}
          </button>
        </div>

        {strategy && (
          <div className="mt-4 grid gap-2 rounded-md bg-[var(--muted,#f8fafc)] p-3 text-sm">
            <p>
              <span className="font-semibold">Hook:</span> {strategy.hook}
            </p>
            <p>
              <span className="font-semibold">Audience:</span> {strategy.audience}
            </p>
            <p>
              <span className="font-semibold">Value:</span> {strategy.value_prop}
            </p>
            <p>
              <span className="font-semibold">CTA:</span> {strategy.cta_angle}
              {strategy.channels.length > 0 && (
                <span className="text-[var(--muted-foreground,#64748b)]">
                  {" "}
                  · Channels: {strategy.channels.join(", ")}
                </span>
              )}
            </p>
          </div>
        )}
      </Surface>

      {error && (
        <div className="mb-4 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-[260px_1fr_300px]">
        <aside>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground,#64748b)]">
            Creatives
          </h2>
          {loading ? (
            <p className="text-sm text-[var(--muted-foreground,#64748b)]">Loading…</p>
          ) : designs.length === 0 ? (
            <p className="text-sm text-[var(--muted-foreground,#64748b)]">
              No creatives yet — generate a campaign above.
            </p>
          ) : (
            <ul className="space-y-1">
              {designs.map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => void open(d.id)}
                    className="w-full rounded-md px-3 py-2 text-left text-sm hover:bg-[var(--muted,#f1f5f9)]"
                    style={{
                      background:
                        selected?.id === d.id ? "var(--muted,#f1f5f9)" : undefined,
                    }}
                  >
                    <span className="block truncate font-medium">{d.name}</span>
                    <span className="text-[11px] text-[var(--muted-foreground,#94a3b8)]">
                      v{d.current_revision} · {d.media_type}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section>
          {selected ? (
            <>
              <div className="mb-2 inline-flex rounded-md border border-[var(--border,#e2e8f0)] p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => setEditMode(false)}
                  className="rounded px-2.5 py-1"
                  style={{ background: !editMode ? "var(--muted,#f1f5f9)" : undefined }}
                >
                  Preview
                </button>
                <button
                  type="button"
                  onClick={() => setEditMode(true)}
                  className="rounded px-2.5 py-1"
                  style={{ background: editMode ? "var(--muted,#f1f5f9)" : undefined }}
                >
                  Edit
                </button>
              </div>

              {editMode ? (
                <EditorShell
                  design={selected}
                  onSaved={async () => {
                    await refreshDesigns();
                    void open(selected.id);
                  }}
                />
              ) : (
                <>
                  {previewDoc && (
                    <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--primary,#2563eb)]">
                      Preview — not saved yet
                    </p>
                  )}
                  <DesignViewer doc={previewDoc ?? selected.doc} />
                  <NlEditPanel
                    designId={selected.id}
                    baseRevision={selected.current_revision}
                    onPreviewDoc={setPreviewDoc}
                    onCommitted={async (res) => {
                      setPreviewDoc(null);
                      const items = await refreshDesigns();
                      const next =
                        res.created_design_ids[0] ??
                        (items.find((d) => d.id === selected.id)?.id ?? items[0]?.id);
                      if (next) void open(next);
                    }}
                  />
                  {selected.media_type === "video" && <VideoPanel designId={selected.id} />}
                </>
              )}
            </>
          ) : (
            <Surface className="grid h-full min-h-[320px] place-items-center text-sm text-[var(--muted-foreground,#64748b)]">
              Generate a campaign, then select a creative to preview.
            </Surface>
          )}
        </section>

        <aside>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground,#64748b)]">
            History
          </h2>
          <RevisionHistory
            revisions={revisions}
            currentRevision={selected?.current_revision}
          />
        </aside>
      </div>
    </div>
  );
}
