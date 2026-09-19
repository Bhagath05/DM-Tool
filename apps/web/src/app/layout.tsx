import type { Metadata } from "next";

import { AuthProvider } from "@/components/auth-provider";
import { CookieConsent } from "@/components/cookie-consent";
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
  return (
    <html lang="en">
      {/* suppressHydrationWarning: browser extensions (Grammarly, etc.)
          inject attributes into <body> after hydration, causing benign mismatches. */}
      <body className="min-h-screen antialiased" suppressHydrationWarning>
        <AuthProvider>{children}</AuthProvider>
        <CookieConsent />
      </body>
    </html>
  );
}
