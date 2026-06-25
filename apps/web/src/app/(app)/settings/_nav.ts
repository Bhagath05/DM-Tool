/**
 * Phase 10.1 — Settings sub-nav definition.
 *
 * Extracted from `layout.tsx` because Next.js App Router forbids
 * arbitrary named exports from a `layout.tsx`. The constant lives
 * here so both the layout and tests can import it without violating
 * the framework contract.
 *
 * Anything that needs to enumerate settings routes (sub-nav, tests,
 * command palette, future docs) should import from this module.
 */

import {
  Bell,
  Building2,
  CreditCard,
  Gauge,
  type LucideIcon,
  Plug,
  ShieldCheck,
  Users2,
} from "lucide-react";

export interface SettingsNavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  description: string;
}

export const SETTINGS_NAV: SettingsNavItem[] = [
  {
    href: "/settings/organization",
    label: "Organization",
    icon: Building2,
    description: "Company profile, branding, locale.",
  },
  {
    href: "/settings/team",
    label: "Team",
    icon: Users2,
    description: "Members, roles, invitations.",
  },
  {
    href: "/settings/billing",
    label: "Billing",
    icon: CreditCard,
    description: "Plan, invoices, upgrade.",
  },
  {
    href: "/settings/integrations",
    label: "Integrations",
    icon: Plug,
    description: "Connect ad platforms + CRMs.",
  },
  {
    href: "/settings/notifications",
    label: "Notifications",
    icon: Bell,
    description: "Email preferences and alerts.",
  },
  {
    href: "/settings/security",
    label: "Security",
    icon: ShieldCheck,
    description: "Sessions, passwords, MFA.",
  },
  {
    href: "/settings/usage",
    label: "Usage & Limits",
    icon: Gauge,
    description: "Platform usage and plan caps.",
  },
];
