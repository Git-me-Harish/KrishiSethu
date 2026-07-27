import { NextResponse, type NextRequest } from "next/server";

/**
 * Server-side route protection for /dashboard.
 *
 * Every dashboard page previously gated itself in a client component — and
 * two of them (dashboard/admin/audit, dashboard/privacy) forgot to. That
 * means the page HTML and its client bundle ship to anyone who asks for the
 * URL, and the "guard" is a redirect that runs after React has already
 * mounted the page. Unauthenticated visitors saw a flash of the real UI.
 *
 * Middleware runs before any of that. It cannot read localStorage (there is
 * no browser yet), so it gates on `krishisetu_session` — a contentless
 * marker cookie written alongside the tokens in lib/api/client.ts.
 *
 * This is a UX/exposure boundary, NOT an authorization boundary. The cookie
 * carries no credential and is trivially forgeable; what it prevents is
 * shipping dashboard shells to logged-out visitors. Authorization remains
 * where it belongs: the API validating the Bearer token on every request,
 * which is why a forged cookie yields a dashboard whose every fetch 401s.
 */

const SESSION_MARKER_COOKIE = "krishisetu_session";

export function middleware(request: NextRequest) {
  if (request.cookies.has(SESSION_MARKER_COOKIE)) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  // Preserve where they were headed so login can send them back. Only the
  // path is carried over — never the full URL, which would make this an
  // open-redirect gadget.
  loginUrl.searchParams.set(
    "next",
    request.nextUrl.pathname + request.nextUrl.search,
  );

  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
