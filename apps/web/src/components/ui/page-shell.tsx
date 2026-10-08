/**
 * Page frame primitives (Phase 6.6) — the canonical page layout.
 *
 * Before this, every page invented its own wrapper: max-w-6xl here,
 * max-w-7xl there, some adding their own padding on top of the (app)
 * layout's, spacing drifting between gap-6 / gap-8 / gap-12. These
 * primitives give one max-width, one rhythm, one header shape, so the
 * product reads as a single surface.
 *
 *   <PageShell>            consistent max-width + vertical rhythm
 *     <PageHeader …/>      eyebrow · title (one <h1>) · description · actions,
 *                          with an optional sub-nav row (tabs) above the title
 *     <Section …>          a band within the page (optional heading + body)
 *     <Toolbar>            a filter/action row
 *     <ContentGrid cols>   a responsive grid
 *   </PageShell>
 *
 * Card discipline lives OUTSIDE these: a Section is not a card. Use cards
 * only when grouping genuinely aids comprehension (see Surface).
 */

import { AlertTriangle } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const WIDTH_CLS = {
  narrow: "max-w-3xl",
  default: "max-w-6xl",
  wide: "max-w-7xl",
  full: "max-w-none",
} as const;

export interface PageShellProps
  extends React.HTMLAttributes<HTMLDivElement> {
  /** Max content width. narrow=forms, default=most pages, wide=dense data. */
  width?: keyof typeof WIDTH_CLS;
}

export function PageShell({
  width = "default",
  className,
  children,
  ...rest
}: PageShellProps) {
  return (
    <div
      {...rest}
      className={cn(
        "mx-auto flex w-full flex-col gap-8",
        WIDTH_CLS[width],
        className,
      )}
    >
      {children}
    </div>
  );
}

export interface PageHeaderProps {
  /** Short uppercase eyebrow above the title. */
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  /** Right-aligned actions — buttons, links. */
  actions?: ReactNode;
  /** Sub-navigation (e.g. BrainTabs / MeasureTabs) rendered above the title. */
  nav?: ReactNode;
  className?: string;
  "data-testid"?: string;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  nav,
  className,
  "data-testid": testId,
}: PageHeaderProps) {
  return (
    <header
      data-testid={testId ?? "page-header"}
      className={cn("flex flex-col gap-4", className)}
    >
      {nav}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1.5">
          {eyebrow && (
            <span className="text-meta text-ai-soft-foreground">{eyebrow}</span>
          )}
          <h1 className="text-page-title text-foreground">{title}</h1>
          {description && (
            <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
              {description}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {actions}
          </div>
        )}
      </div>
    </header>
  );
}

export interface SectionProps
  extends Omit<React.HTMLAttributes<HTMLElement>, "title"> {
  title?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}

export function Section({
  title,
  description,
  action,
  className,
  children,
  ...rest
}: SectionProps) {
  return (
    <section className={cn("flex flex-col gap-4", className)} {...rest}>
      {(title || action) && (
        <div className="flex items-end justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-1">
            {title && (
              <h2 className="text-card-title text-foreground">{title}</h2>
            )}
            {description && (
              <p className="max-w-prose text-sm text-muted-foreground">
                {description}
              </p>
            )}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Toolbar({
  className,
  children,
  ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-3",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

const GRID_COLS = {
  1: "grid-cols-1",
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
  4: "grid-cols-2 lg:grid-cols-4",
} as const;

export function ContentGrid({
  cols = 3,
  className,
  children,
  ...rest
}: React.HTMLAttributes<HTMLDivElement> & { cols?: keyof typeof GRID_COLS }) {
  return (
    <div className={cn("grid gap-4", GRID_COLS[cols], className)} {...rest}>
      {children}
    </div>
  );
}

export interface ErrorStateProps {
  title?: string;
  description?: ReactNode;
  icon?: LucideIcon;
  action?: ReactNode;
  className?: string;
  "data-testid"?: string;
}

/**
 * Completes the Empty/Loading/Error trio (see EmptyState + Skeleton).
 * role="alert" so assistive tech announces it; danger tone via tokens,
 * never color alone — the icon + heading carry the meaning too.
 */
export function ErrorState({
  title = "Something went wrong",
  description = "We couldn't load this right now. Please try again.",
  icon: Icon = AlertTriangle,
  action,
  className,
  "data-testid": testId,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      data-testid={testId ?? "error-state"}
      className={cn(
        "flex flex-col items-center gap-3 rounded-xl border border-bad-border bg-bad-soft px-6 py-10 text-center",
        className,
      )}
    >
      <Icon className="h-6 w-6 text-bad" aria-hidden />
      <div className="flex flex-col gap-1">
        <p className="font-medium text-foreground">{title}</p>
        <p className="text-sm text-bad-soft-foreground">{description}</p>
      </div>
      {action}
    </div>
  );
}
