import type { Metadata } from "next";

import { AuthProvider } from "@/components/auth-provider";
import { CookieConsent } from "@/components/cookie-consent";
import { THEME_INIT_SCRIPT } from "@/lib/theme";
import "./globals.css";

export const metadata: Metadata = {
  title: "DM Tool",
  description: "Your AI digital marketing advisor",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Next.js App Router rule: <html> and <body> MUST be the literal root
  // of the layout's returned JSX, so any client provider is nested INSIDE
  // <body> rather than wrapping it. `AuthProvider` is a thin pass-through
  // under first-party auth (login state comes from TenantProvider's /me
  // call), kept as a stable mount point.
  //
  // suppressHydrationWarning on <html>: the theme bootstrap script mutates
  // the data-theme attribute before React hydrates, so the server/client
  // attribute set legitimately differs on first paint.
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* FOUC guard: apply the persisted theme to <html> before first
            paint, so a forced Light/Dark choice never flashes the other
            theme. Dependency-free + try/catch'd in THEME_INIT_SCRIPT. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      {/* suppressHydrationWarning: browser extensions (Grammarly, etc.)
          inject attributes into <body> after hydration, causing benign mismatches. */}
      <body className="min-h-screen antialiased" suppressHydrationWarning>
        <AuthProvider>{children}</AuthProvider>
        <CookieConsent />
      </body>
    </html>
  );
}
