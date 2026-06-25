import type { Metadata } from "next";

import { AuthProvider } from "@/components/auth-provider";
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
  // of the layout's returned JSX. Wrapping them in a client component
  // (as we did previously with `<AuthProvider>` outside) breaks two
  // invariants simultaneously:
  //
  //   1. Structural — the App Router framework expects to manage
  //      <html>/<body> directly; wrapping causes hydration anomalies.
  //
  //   2. Hooks — AuthProvider conditionally renders <ClerkProvider> +
  //      <ClerkTokenBridge> (which call hooks internally) vs. a bare
  //      Fragment, based on `isClerkConfigured()`. When the condition
  //      flips between the server-rendered tree and the client-hydrated
  //      tree (env var resolution timing in dev / streamed RSC), the
  //      hook count of the wrapped subtree changes → React throws
  //      "Rendered more hooks than during the previous render."
  //
  // Nesting AuthProvider INSIDE <body> stabilises both: <html>/<body>
  // are always the root, and any conditional rendering happens at a
  // child level where React handles tree-shape changes cleanly.
  return (
    <html lang="en">
      {/* suppressHydrationWarning: browser extensions (Grammarly, etc.)
          inject attributes into <body> after hydration, causing benign mismatches. */}
      <body className="min-h-screen antialiased" suppressHydrationWarning>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
