import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

// Inline the AUTH_MODE check rather than import from lib/ — Next.js
// middleware runs at the edge and module-level imports add to the edge
// bundle size. This duplicates the logic from lib/clerk-config.ts, but
// the duplication is trivial (two env reads). Keep both in sync.
const rawMode = process.env.NEXT_PUBLIC_AUTH_MODE;
const authMode: "demo" | "clerk" | "hybrid" =
  rawMode === "clerk" ? "clerk" : rawMode === "hybrid" ? "hybrid" : "demo";

const PLACEHOLDER_RX = /^(pk_test_replace_me|)$/;
const hasValidClerkKey = !PLACEHOLDER_RX.test(
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "",
);

// Three-state middleware behaviour:
//   demo                              → pure pass-through, no Clerk
//   clerk + key                       → Clerk session + ENFORCE auth.protect
//   hybrid + key                      → Clerk session available, NO protect
//                                       (anonymous /dashboard works as demo)
//   anything + no key                 → pure pass-through (degraded but safe)
const clerkSessionActive =
  (authMode === "clerk" || authMode === "hybrid") && hasValidClerkKey;
const enforceAuth = authMode === "clerk" && hasValidClerkKey;

const isPublicRoute = createRouteMatcher([
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
]);

// In clerk mode: protect non-public routes (forces sign-in).
const strictMiddleware = clerkMiddleware(async (auth, req) => {
  if (!isPublicRoute(req)) {
    await auth.protect();
  }
});

// In hybrid mode: mount Clerk session helpers but DO NOT call
// `auth.protect()`. This lets anonymous visitors reach /dashboard
// (where the backend resolves them as demo-user) AND lets signed-in
// visitors carry a valid session into the same routes.
const openMiddleware = clerkMiddleware(async () => {
  /* no-op — Clerk just attaches its session helpers to the request */
});

export default enforceAuth
  ? strictMiddleware
  : clerkSessionActive
  ? openMiddleware
  : () => NextResponse.next();

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
