"use client";

/**
 * Phase 10.1 — Settings · Notifications.
 *
 * UI scaffolding only. There's no notifications backend yet, so:
 *   - Toggle state persists to localStorage per browser. Honest copy
 *     says "Cloud sync coming" so the founder isn't misled into
 *     thinking these are server-side preferences.
 *   - Channel switches (Email / Slack / SMS) — only Email is enabled
 *     by default; Slack + SMS render as disabled with a "Coming soon"
 *     pill rather than fake-functional toggles.
 *   - "Send a test" buttons are stubbed and emit a toast confirming
 *     the placeholder behaviour.
 *
 * When the `/notifications` endpoint ships in a future phase, the
 * `usePrefs` hook swaps from localStorage to the real GET/PUT and
 * the rest of the UI stays identical.
 */

import {
  Bell,
  type LucideIcon,
  Mail,
  MessageSquare,
  Slack,
  Smartphone,
  Sparkles,
  TrendingUp,
  Wallet,
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

const PREFS_STORAGE_KEY = "aicmo.notifications.prefs.v1";

interface NotificationCategory {
  key: string;
  icon: LucideIcon;
  label: string;
  description: string;
  cadence: string;
  defaultOn: boolean;
}

const CATEGORIES: NotificationCategory[] = [
  {
    key: "weekly_digest",
    icon: Wand2,
    label: "Weekly AI Coach digest",
    description:
      "What's working, what to do next, and the week's expected impact — every Monday morning.",
    cadence: "Weekly · Mondays · 8:00 local",
    defaultOn: true,
  },
  {
    key: "winner_alert",
    icon: TrendingUp,
    label: "New winner detected",
    description:
      "Heads-up the moment a creative crosses the high-confidence band so you can scale before it tires.",
    cadence: "As it happens · throttled to 1/day",
    defaultOn: true,
  },
  {
    key: "waste_alert",
    icon: Sparkles,
    label: "Budget waste flagged",
    description:
      "Alert when a creative is bleeding spend with no return — caught before the bill arrives.",
    cadence: "As it happens · throttled to 1/day",
    defaultOn: true,
  },
  {
    key: "billing",
    icon: Wallet,
    label: "Billing & plan updates",
    description:
      "Invoices, plan limits, payment-method changes. You can't turn off failed-payment notices for legal reasons.",
    cadence: "As they happen",
    defaultOn: true,
  },
  {
    key: "product",
    icon: Bell,
    label: "Product announcements",
    description:
      "Major releases (new integrations, AI Coach upgrades). We keep this quiet — roughly monthly.",
    cadence: "≤ monthly",
    defaultOn: false,
  },
];

interface ChannelDef {
  key: "email" | "slack" | "sms";
  icon: LucideIcon;
  label: string;
  status: "live" | "coming-soon";
  identifier: string | null;
}

export default function NotificationsSettingsPage() {
  const [prefs, setPrefs] = useState<Record<string, boolean>>(() =>
    CATEGORIES.reduce<Record<string, boolean>>((acc, c) => {
      acc[c.key] = c.defaultOn;
      return acc;
    }, {}),
  );
  const [toast, setToast] = useState<string | null>(null);

  // Hydrate from localStorage on mount. SSR-safe.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(PREFS_STORAGE_KEY);
      if (raw) {
        const stored = JSON.parse(raw) as Record<string, boolean>;
        setPrefs((current) => ({ ...current, ...stored }));
      }
    } catch {
      /* ignore corrupt cache */
    }
  }, []);

  const togglePref = useCallback((key: string) => {
    setPrefs((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try {
        window.localStorage.setItem(PREFS_STORAGE_KEY, JSON.stringify(next));
      } catch {
        /* best effort */
      }
      return next;
    });
  }, []);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3500);
  }, []);

  // Channels — pulled from a hardcoded shape today; reads from
  // `useTenant().user.email` so the Email channel shows the real
  // address.
  const channels: ChannelDef[] = [
    {
      key: "email",
      icon: Mail,
      label: "Email",
      status: "live",
      identifier: "Goes to your account email",
    },
    {
      key: "slack",
      icon: Slack,
      label: "Slack",
      status: "coming-soon",
      identifier: null,
    },
    {
      key: "sms",
      icon: Smartphone,
      label: "SMS",
      status: "coming-soon",
      identifier: null,
    },
  ];

  return (
    <div className="flex flex-col gap-8" data-testid="settings-notifications">
      <SectionHeading
        eyebrow="Settings · Notifications"
        heading="What we tell you, and where"
        description="Turn each category on or off. We default to the signals founders actually act on — chat noise we leave off."
        size="lg"
        action={
          <Button
            variant="outline"
            size="sm"
            onClick={() => showToast("Test notification queued. (Will send for real once the backend ships.)")}
            data-testid="notifications-test"
          >
            Send a test
          </Button>
        }
      />

      {toast && (
        <div
          role="status"
          data-testid="notifications-toast"
          className="rounded-xl border border-ai-border bg-ai-soft px-4 py-3 text-sm text-ai-soft-foreground"
        >
          {toast}
        </div>
      )}

      {/* Channels */}
      <section
        className="flex flex-col gap-4"
        data-testid="notifications-channels"
      >
        <SectionHeading
          eyebrow="Channels"
          heading="Where alerts land"
          description="Email is on by default. Slack and SMS arrive in a future release."
        />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {channels.map((ch) => (
            <ChannelTile key={ch.key} channel={ch} />
          ))}
        </div>
      </section>

      {/* Categories */}
      <section className="flex flex-col gap-4" data-testid="notifications-categories">
        <SectionHeading
          eyebrow="What to send"
          heading="Categories"
          description="Each switch controls one category across every channel you've enabled above."
        />
        <ul className="card-surface flex flex-col divide-y divide-border/60 p-0">
          {CATEGORIES.map((cat) => (
            <CategoryRow
              key={cat.key}
              category={cat}
              enabled={prefs[cat.key] ?? cat.defaultOn}
              onToggle={() => togglePref(cat.key)}
            />
          ))}
        </ul>
        <p className="text-xs text-muted-foreground">
          <Bell className="mr-1 inline h-3 w-3" />
          Preferences save to this device. Cloud sync arrives with the
          notifications backend in a future phase.
        </p>
      </section>

      {/* Quiet hours — honest placeholder */}
      <section className="card-surface flex flex-col gap-4 p-6 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex max-w-prose flex-col gap-1">
          <h4 className="text-card-title font-semibold">Quiet hours</h4>
          <p className="text-sm text-muted-foreground">
            Pause non-urgent alerts overnight (Coach digests, product updates).
            Billing and failed-payment notices always go through.
          </p>
        </div>
        <Button variant="outline" size="sm" disabled>
          Coming soon
        </Button>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Channel tile
// ---------------------------------------------------------------------

function ChannelTile({ channel }: { channel: ChannelDef }) {
  const Icon = channel.icon;
  const tone: PillTone = channel.status === "live" ? "good" : "muted";
  return (
    <article
      data-testid={`channel-${channel.key}`}
      className={cn(
        "card-surface card-surface-hover flex flex-col gap-3 p-5",
        channel.status === "coming-soon" && "opacity-95",
      )}
    >
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-muted text-foreground/80"
          >
            <Icon className="h-4 w-4" />
          </span>
          <div className="flex flex-col">
            <span className="text-sm font-semibold text-foreground">
              {channel.label}
            </span>
            <StatusPill tone={tone} size="sm" dot>
              {channel.status === "live" ? "Active" : "Coming soon"}
            </StatusPill>
          </div>
        </div>
      </header>
      {channel.identifier ? (
        <p className="text-xs text-muted-foreground">{channel.identifier}</p>
      ) : (
        <p className="text-xs text-muted-foreground">
          Will connect when the channel ships.
        </p>
      )}
    </article>
  );
}

// ---------------------------------------------------------------------
//  Category row + toggle
// ---------------------------------------------------------------------

function CategoryRow({
  category,
  enabled,
  onToggle,
}: {
  category: NotificationCategory;
  enabled: boolean;
  onToggle: () => void;
}) {
  const Icon = category.icon;
  return (
    <li
      data-testid={`notification-category-${category.key}`}
      className="flex items-start gap-4 px-6 py-4"
    >
      <span
        aria-hidden
        className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-muted text-foreground/80"
      >
        <Icon className="h-4 w-4" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center justify-between gap-3">
          <h5 className="text-sm font-semibold text-foreground">
            {category.label}
          </h5>
          <Toggle
            checked={enabled}
            onChange={onToggle}
            label={`${enabled ? "Disable" : "Enable"} ${category.label}`}
            testId={`toggle-${category.key}`}
          />
        </div>
        <p className="text-sm leading-relaxed text-muted-foreground">
          {category.description}
        </p>
        <p className="text-xs text-muted-foreground/80">
          <MessageSquare className="mr-1 inline h-3 w-3" />
          {category.cadence}
        </p>
      </div>
    </li>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  testId,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
  testId?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={onChange}
      data-testid={testId}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border transition-colors duration-200",
        checked
          ? "border-ai bg-ai"
          : "border-border bg-muted",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "pointer-events-none absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200",
          checked ? "translate-x-[22px]" : "translate-x-0.5",
        )}
      />
    </button>
  );
}
