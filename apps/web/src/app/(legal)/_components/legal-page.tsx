/**
 * Shared shell for the legal pages (Terms, Privacy, Cookies).
 *
 * IMPORTANT: these pages are production-grade SCAFFOLDING only. Every
 * substantive clause is a placeholder marked `TODO: Replace with
 * lawyer-approved text.` and the page carries a visible draft banner. No
 * binding legal promise is authored here — the content is the customer's
 * (and their counsel's) to own. Do not remove the banner until real,
 * reviewed copy replaces the placeholders.
 */

import Link from "next/link";

export function LegalPage({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: React.ReactNode;
}) {
  return (
    <article className="flex flex-col gap-6">
      <div
        role="note"
        className="rounded-lg border border-amber-400/40 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-400/30 dark:bg-amber-950/40 dark:text-amber-200"
      >
        <strong>Draft — pending legal review.</strong> This is a template, not a
        binding agreement. Every section marked{" "}
        <code className="rounded bg-amber-100 px-1 dark:bg-amber-900/50">
          TODO
        </code>{" "}
        must be replaced with text approved by qualified legal counsel before
        launch.
      </div>

      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">Last updated: {updated}</p>
      </header>

      <div className="flex flex-col gap-6 text-sm leading-relaxed text-foreground/90">
        {children}
      </div>

      <footer className="mt-4 flex flex-wrap gap-4 border-t border-border pt-4 text-sm text-muted-foreground">
        <Link
          href={"/terms" as never}
          className="hover:text-foreground hover:underline"
        >
          Terms of Service
        </Link>
        <Link
          href={"/privacy" as never}
          className="hover:text-foreground hover:underline"
        >
          Privacy Policy
        </Link>
        <Link
          href={"/cookies" as never}
          className="hover:text-foreground hover:underline"
        >
          Cookie Policy
        </Link>
        <Link href="/" className="ml-auto hover:text-foreground hover:underline">
          ← Back to DM Tool
        </Link>
      </footer>
    </article>
  );
}

/** A titled clause with a required lawyer-review marker. */
export function Clause({
  heading,
  children,
}: {
  heading: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-1.5">
      <h2 className="text-base font-semibold text-foreground">{heading}</h2>
      {children}
      <p className="text-xs font-medium text-amber-700 dark:text-amber-300">
        {/* TODO: Replace with lawyer-approved text. */}
        TODO: Replace with lawyer-approved text.
      </p>
    </section>
  );
}
