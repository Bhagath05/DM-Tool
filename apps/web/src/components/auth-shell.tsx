import Link from "next/link";
import type { ReactNode } from "react";

import { Check } from "lucide-react";

/**
 * Premium, responsive shell around Clerk's <SignIn>/<SignUp>. Two columns on
 * desktop (brand story + form), single column on mobile. Uses DM Tool design
 * tokens only — it wraps Clerk, it does not replace it. All auth logic stays in
 * Clerk (sign-in, sign-up, forgot-password, reset, Google, session).
 */

const VALUE_PROPS = [
  "Real marketing evidence — never vanity metrics.",
  "AI recommendations you approve before anything publishes.",
  "Analytics that tell you exactly what to do next.",
];

export function AuthShell({
  title,
  subtitle,
  altPrompt,
  altHref,
  altLabel,
  children,
}: {
  title: string;
  subtitle: string;
  altPrompt: string;
  altHref: string;
  altLabel: string;
  children: ReactNode;
}) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Brand panel — desktop only */}
      <aside className="relative hidden overflow-hidden bg-primary text-primary-foreground lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              "radial-gradient(60% 60% at 20% 10%, hsl(0 0% 100% / 0.12), transparent 70%), radial-gradient(50% 50% at 90% 90%, hsl(0 0% 100% / 0.10), transparent 70%)",
          }}
        />
        <div className="relative">
          <Wordmark className="text-primary-foreground" />
        </div>
        <div className="relative max-w-md">
          <h2 className="text-3xl font-semibold leading-tight tracking-tight">
            Your AI digital marketing advisor.
          </h2>
          <p className="mt-3 text-sm text-primary-foreground/80">
            Get more leads and customers — every day. No marketing background
            required.
          </p>
          <ul className="mt-8 space-y-3">
            {VALUE_PROPS.map((v) => (
              <li key={v} className="flex items-start gap-2.5 text-sm">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary-foreground/15">
                  <Check className="h-3 w-3" />
                </span>
                <span className="text-primary-foreground/90">{v}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-primary-foreground/60">
          Nothing is published without your explicit approval.
        </p>
      </aside>

      {/* Form panel */}
      <main className="flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-md space-y-6">
          <div className="lg:hidden">
            <Wordmark />
          </div>
          <header className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            <p className="text-sm text-muted-foreground">{subtitle}</p>
          </header>

          {children}

          <p className="text-center text-sm text-muted-foreground">
            {altPrompt}{" "}
            <Link
              href={altHref as never}
              className="font-medium text-primary hover:underline"
            >
              {altLabel}
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}

function Wordmark({ className }: { className?: string }) {
  return (
    <span className={`text-lg font-bold tracking-tight ${className ?? ""}`}>
      DM&nbsp;Tool
    </span>
  );
}
