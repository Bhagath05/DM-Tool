"use client";

/**
 * Root error boundary for the App Router.
 *
 * Next.js requires this file (with the `"use client"` directive and the
 * full <html>/<body> wrapper) to render when an error escapes every
 * other boundary — including errors thrown in the root layout.
 *
 * Sentry's @sentry/nextjs needs us to invoke `Sentry.captureException`
 * from here explicitly; the SDK doesn't auto-instrument this file. See
 * https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/#react-render-errors-in-app-router
 */

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export default function GlobalError({
  error,
}: {
  error: Error & { digest?: string };
}) {
  useEffect(() => {
    Sentry.captureException(error);
    // Surface the full object (incl. any React component stack) to the console.
    console.error("[GlobalError]", error);
  }, [error]);

  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "ui-monospace, monospace", background: "#0b1220", color: "#e2e8f0" }}>
        <div style={{ maxWidth: 900, margin: "0 auto", padding: "40px 24px" }}>
          <h1 style={{ fontSize: 18, color: "#fff" }}>Something broke while loading the app</h1>
          <p style={{ fontSize: 13, color: "#94a3b8" }}>
            This is a render error, not data loss. Details below identify the failing component.
          </p>
          <div style={{ marginTop: 16, display: "flex", gap: 12 }}>
            <button
              onClick={() => window.location.reload()}
              style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid #334155", background: "#1e293b", color: "#fff", cursor: "pointer" }}
            >
              Reload
            </button>
          </div>
          <p style={{ marginTop: 20, fontSize: 13, fontWeight: 600, color: "#f87171" }}>
            {error.name}: {error.message}
          </p>
          {error.digest && (
            <p style={{ fontSize: 12, color: "#94a3b8" }}>digest: {error.digest}</p>
          )}
          <pre
            style={{
              marginTop: 8,
              maxHeight: 460,
              overflow: "auto",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontSize: 11,
              lineHeight: 1.5,
              color: "#cbd5e1",
              background: "#020617",
              padding: 12,
              borderRadius: 8,
              border: "1px solid #1e293b",
            }}
          >
            {error.stack}
          </pre>
        </div>
      </body>
    </html>
  );
}
