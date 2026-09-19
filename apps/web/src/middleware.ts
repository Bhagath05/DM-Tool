import { type NextRequest, NextResponse } from "next/server";

// First-party auth gate. The security boundary is the backend (`require_user`
// validates the session on every request); this middleware is only a UX
// redirect so an unauthenticated user lands on /sign-in instead of a blank
// protected page. It checks presence of the HttpOnly session cookie — it does
// NOT validate it (it can't; that's the backend's job).
const SESSION_COOKIE = "dmt_session";

const PUBLIC_PREFIXES = [
  "/sign-in",
  "/sign-up",
  "/verify-email",
  "/forgot-password",
  "/reset-password",
  // Invite acceptance must be reachable while logged out — the token is the
  // credential; the accept action still requires a signed-in user server-side.
  "/invites",
];

function isPublic(pathname: string): boolean {
  if (pathname === "/") return true;
  return PUBLIC_PREFIXES.some((p) => pathname.startsWith(p));
}

export default function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (isPublic(pathname)) return NextResponse.next();

  if (!req.cookies.has(SESSION_COOKIE)) {
    const url = req.nextUrl.clone();
    url.pathname = "/sign-in";
    url.searchParams.set("redirect_url", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
