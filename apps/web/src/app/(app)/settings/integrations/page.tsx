"use client";

/**
 * Phase 10.1 — Settings · Integrations.
 *
 * Six connector tiles for the platforms the engine will eventually
 * pull data from directly. Every one is honestly labelled "Coming
 * soon" — none are wired today. The card design is the same one
 * we'll reuse when the real OAuth flows land, so the visual hierarchy
 * stays consistent.
 *
 * Two sections:
 *   1. Ad platforms — Meta / Google / LinkedIn / TikTok
 *   2. CRM & marketing tools — HubSpot / Salesforce
 *
 * The only LIVE option today is the CSV upload, which already lives
 * on /overview and /performance — we link to it from the page header
 * so a founder discovers the working path immediately.
 */

import {
  ArrowUpRight,
  CloudUpload,
  type LucideIcon,
  Plug,
} from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { StatusPill } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

import { IntegrationDashboard } from "./_components/integration-dashboard";
import { SocialPublishingConnectors } from "./_components/social-connectors";

export const dynamic = "force-dynamic";

interface Connector {
  key: string;
  name: string;
  description: string;
  /** Inline SVG mark to avoid pulling brand-asset binaries. */
  mark: React.ReactNode;
  pillars: string[];
  status: "coming-soon" | "live";
}

const AD_PLATFORMS: Connector[] = [
  {
    key: "meta",
    name: "Meta Ads",
    description:
      "Pull Facebook + Instagram ad performance directly. No CSV uploads, no manual exports.",
    mark: <MarkMeta />,
    pillars: ["Daily auto-sync", "Creative breakdown", "Audience insights"],
    status: "coming-soon",
  },
  {
    key: "google",
    name: "Google Ads",
    description:
      "Search, Display, YouTube — see what's winning across the Google network with one connection.",
    mark: <MarkGoogle />,
    pillars: ["Search + Display", "Keyword winners", "Cost-per-result"],
    status: "coming-soon",
  },
  {
    key: "linkedin",
    name: "LinkedIn Ads",
    description:
      "B2B campaigns analysed alongside everything else. Track lead-form fills back to source.",
    mark: <MarkLinkedIn />,
    pillars: ["Lead-form attribution", "Job-title targeting", "Account-based"],
    status: "coming-soon",
  },
  {
    key: "tiktok",
    name: "TikTok Ads",
    description:
      "Spark Ads, video formats, creative trends — we'll surface what's working for your audience.",
    mark: <MarkTikTok />,
    pillars: ["Video-format mix", "Creator tags", "Trend overlap"],
    status: "coming-soon",
  },
];

const CRM_TOOLS: Connector[] = [
  {
    key: "hubspot",
    name: "HubSpot",
    description:
      "Pull contacts, deals, and lifecycle stages so the engine can attribute revenue back to creatives.",
    mark: <MarkHubSpot />,
    pillars: ["Deal attribution", "Contact sync", "Lifecycle tracking"],
    status: "coming-soon",
  },
  {
    key: "salesforce",
    name: "Salesforce",
    description:
      "Closed-won revenue feeds the engine's ROAS calculation — the closest thing to the real number.",
    mark: <MarkSalesforce />,
    pillars: ["Opportunity sync", "Pipeline value", "Closed-won feedback"],
    status: "coming-soon",
  },
];

export default function IntegrationsSettingsPage() {
  return (
    <div className="flex flex-col gap-8" data-testid="settings-integrations">
      <SectionHeading
        eyebrow="Settings · Integrations"
        heading="Connect your data"
        description="Direct platform connections so insights stay fresh without manual exports. Available today: CSV upload."
        size="lg"
        action={
          <Button asChild size="sm" variant="outline">
            <Link
              href={"/performance" as never}
              data-testid="integrations-upload-link"
            >
              <CloudUpload className="mr-2 h-3.5 w-3.5" />
              Upload a CSV instead
            </Link>
          </Button>
        }
      />

      {/* Why-direct-connectors band — sets expectations */}
      <article className="card-surface-ai relative overflow-hidden p-6 sm:p-7">
        <div className="flex flex-col gap-2">
          <span className="text-meta text-ai-soft-foreground">
            <Plug className="mr-1 inline h-3 w-3" />
            What changes when you connect
          </span>
          <h3 className="text-card-title font-semibold">
            Live data beats batch uploads.
          </h3>
          <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">
            Today the engine reasons from CSVs you upload. With a direct
            connection it refreshes daily, links spend to revenue end-to-end,
            and surfaces creative fatigue before the cost-per-lead drifts. We'll
            email you the moment each connector goes live.
          </p>
        </div>
      </article>

      {/* Live connectors — social publishing + local business */}
      <section className="flex flex-col gap-4">
        <SectionHeading
          eyebrow="Publishing platforms"
          heading="Connect & publish"
          description="OAuth connections for scheduling and publishing content across platforms."
        />
        <SocialPublishingConnectors />
      </section>

      {/* Phase 6.1 — operations dashboard: health, analytics, activity log */}
      <section className="flex flex-col gap-4">
        <SectionHeading
          eyebrow="Operations"
          heading="Connected apps & activity"
          description="Live health, sync analytics, and the full activity log for every connected integration."
        />
        <IntegrationDashboard />
      </section>

      {/* Ad platforms */}
      <ConnectorSection
        eyebrow="Ad platforms"
        heading="Ads"
        description="One-click connection to the platforms running your campaigns today."
        connectors={AD_PLATFORMS}
      />

      {/* CRM & marketing */}
      <ConnectorSection
        eyebrow="CRM & marketing"
        heading="Pipeline & revenue"
        description="Tie creatives back to revenue so ROAS isn't a guess."
        connectors={CRM_TOOLS}
      />

      {/* Footer — request-a-connector affordance */}
      <article className="card-surface flex flex-col items-start justify-between gap-4 p-6 sm:flex-row sm:items-center">
        <div className="flex flex-col gap-1">
          <h4 className="text-card-title font-semibold">
            Need a connector that's not listed?
          </h4>
          <p className="text-sm text-muted-foreground">
            Tell us what you're using — we prioritise the integrations real
            founders ask for.
          </p>
        </div>
        <Button asChild size="sm" variant="outline">
          <a
            href="mailto:hello@dm.tool?subject=Integration%20request"
            data-testid="integrations-request"
          >
            Request a connector
            <ArrowUpRight className="ml-1.5 h-3.5 w-3.5" />
          </a>
        </Button>
      </article>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Section + tile primitives
// ---------------------------------------------------------------------

function ConnectorSection({
  eyebrow,
  heading,
  description,
  connectors,
}: {
  eyebrow: string;
  heading: string;
  description: string;
  connectors: Connector[];
}) {
  return (
    <section
      data-testid={`integrations-section-${heading.toLowerCase().replace(/\s+/g, "-")}`}
      className="flex flex-col gap-4"
    >
      <SectionHeading
        eyebrow={eyebrow}
        heading={heading}
        description={description}
      />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {connectors.map((c) => (
          <ConnectorTile key={c.key} connector={c} />
        ))}
      </div>
    </section>
  );
}

function ConnectorTile({ connector }: { connector: Connector }) {
  return (
    <article
      data-testid={`integration-${connector.key}`}
      className={cn(
        "card-surface card-surface-hover flex flex-col gap-4 p-5 sm:p-6",
        connector.status === "coming-soon" && "opacity-95",
      )}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-border bg-card shadow-xs"
          >
            {connector.mark}
          </span>
          <div className="flex flex-col gap-0.5">
            <h4 className="text-card-title font-semibold text-foreground">
              {connector.name}
            </h4>
            <StatusPill
              tone={connector.status === "live" ? "good" : "muted"}
              size="sm"
              dot
            >
              {connector.status === "live" ? "Connected" : "Coming soon"}
            </StatusPill>
          </div>
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={connector.status === "coming-soon"}
          aria-label={`Connect ${connector.name}`}
          data-testid={`integration-${connector.key}-connect`}
        >
          {connector.status === "live" ? "Manage" : "Connect"}
        </Button>
      </header>

      <p className="text-sm leading-relaxed text-muted-foreground">
        {connector.description}
      </p>

      <ul className="mt-1 flex flex-wrap gap-1.5">
        {connector.pillars.map((p) => (
          <li key={p}>
            <StatusPill tone="neutral" size="sm">
              {p}
            </StatusPill>
          </li>
        ))}
      </ul>
    </article>
  );
}

// ---------------------------------------------------------------------
//  Brand marks — minimal SVG so we don't ship any third-party assets.
//  These are abstract glyphs (not real logos) for the platform names.
// ---------------------------------------------------------------------

function MarkMeta() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <defs>
        <linearGradient id="m-meta" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#1877F2" />
          <stop offset="1" stopColor="#6E47FF" />
        </linearGradient>
      </defs>
      <path
        d="M3 13c0-5 3-9 7-9s5 3 8 8c2 4 2 6 0 7-2 2-5-2-7-5-2-3-3-5-5-5-1 0-2 1-2 4z"
        fill="none"
        stroke="url(#m-meta)"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MarkGoogle() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <circle cx="12" cy="12" r="9" fill="none" stroke="#EA4335" strokeWidth="2" />
      <path d="M12 3a9 9 0 0 1 9 9h-9z" fill="#FBBC05" />
      <path d="M21 12a9 9 0 0 1-9 9v-9z" fill="#34A853" />
      <path d="M12 21a9 9 0 0 1-9-9h9z" fill="#4285F4" />
    </svg>
  );
}

function MarkLinkedIn() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="3" fill="#0A66C2" />
      <rect x="6.5" y="9" width="2.5" height="9" fill="white" />
      <circle cx="7.75" cy="6.75" r="1.5" fill="white" />
      <path
        d="M11 9h2.4v1.3c.5-.9 1.6-1.5 2.8-1.5 2 0 2.8 1.4 2.8 3.3V18h-2.5v-5c0-1.1-.5-1.7-1.4-1.7s-1.6.7-1.6 1.8V18H11z"
        fill="white"
      />
    </svg>
  );
}

function MarkTikTok() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <path
        d="M14 3v9.6a3.4 3.4 0 1 1-3.4-3.4"
        fill="none"
        stroke="#25F4EE"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
      <path
        d="M16 3v9.6a3.4 3.4 0 1 1-3.4-3.4M14 3c.8 2 2.4 3.4 5 3.6"
        fill="none"
        stroke="#FE2C55"
        strokeWidth="2.2"
        strokeLinecap="round"
        transform="translate(-2 0)"
      />
    </svg>
  );
}

function MarkHubSpot() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <circle cx="15" cy="15" r="4" fill="none" stroke="#FF7A59" strokeWidth="2" />
      <circle cx="15" cy="5" r="2.4" fill="none" stroke="#FF7A59" strokeWidth="2" />
      <path d="M15 7.4V11M11.8 12.5L7 8" stroke="#FF7A59" strokeWidth="2" strokeLinecap="round" />
      <circle cx="6" cy="6.5" r="1.5" fill="#FF7A59" />
    </svg>
  );
}

function MarkSalesforce() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <path
        d="M5 13a4 4 0 0 1 4-4 4.5 4.5 0 0 1 7 1 3.5 3.5 0 0 1 3 6 3.5 3.5 0 0 1-4 3 4 4 0 0 1-7-1 3.5 3.5 0 0 1-3-5z"
        fill="#00A1E0"
      />
    </svg>
  );
}
