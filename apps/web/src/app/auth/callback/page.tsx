"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, ShieldCheck, XCircle } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { authApi } from "@/lib/api/client";

/** Error codes the backend is allowed to send us, plus our own local ones. */
const KNOWN_ERROR_CODES = [
  "google_denied",
  "google_auth_failed",
  "google_server_error",
  "google_invalid_callback",
  "google_missing_code",
  "google_completion_failed",
] as const;

type KnownErrorCode = (typeof KNOWN_ERROR_CODES)[number];

/**
 * Reduce an arbitrary query param to a code we recognise.
 *
 * The value is attacker-controllable (anyone can link to
 * /auth/callback?error=<anything>), and it is about to be reflected into a
 * URL we navigate to. Allow-listing it means nothing unexpected can be
 * smuggled through, and encodeURIComponent at the call site handles the rest.
 */
function normalizeErrorCode(raw: string | null): KnownErrorCode {
  if (raw && (KNOWN_ERROR_CODES as readonly string[]).includes(raw)) {
    return raw as KnownErrorCode;
  }
  return "google_auth_failed";
}

/**
 * Google OAuth callback page.
 *
 * The backend's /auth/google/callback handler exchanges the Google
 * authorization code, issues KrishiSetu JWT tokens, stores them behind a
 * single-use 60-second code, and redirects here:
 *
 *   /auth/callback?code=...
 *
 * The tokens themselves are never placed in the URL — a 30-day refresh token
 * in the query string ends up in browser history, the Referer header and
 * every proxy log on the path.
 *
 * On error the backend redirects straight to /login?error=... instead.
 *
 * This page:
 * 1. Reads the single-use `code` from the URL
 * 2. Redeems it via POST /auth/google/exchange (tokens + user in the body)
 * 3. Pushes the user straight into the auth store
 * 4. Redirects to /dashboard
 */
export default function AuthCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setSession = useAuthStore((s) => s.setSession);
  const hydrate = useAuthStore((s) => s.hydrate);
  const processed = useRef(false);

  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState<string>("");

  useEffect(() => {
    // Prevent double-execution in StrictMode. The exchange code is single-use,
    // so a second redemption would fail and bounce the user to /login.
    if (processed.current) return;
    processed.current = true;

    // Every redirect below is deferred, and an unmounted component that later
    // calls router.replace() yanks the user off whatever page they have since
    // navigated to. Collect the timers and clear them on unmount.
    const timers: ReturnType<typeof setTimeout>[] = [];
    let cancelled = false;

    const redirectTo = (path: string, delayMs: number) => {
      timers.push(
        setTimeout(() => {
          if (!cancelled) router.replace(path);
        }, delayMs),
      );
    };

    const fail = (code: KnownErrorCode, message: string) => {
      setStatus("error");
      setErrorMessage(message);
      // Re-derive session state from storage so the rest of the app isn't
      // left waiting on a hydration that this page skipped.
      void hydrate();
      redirectTo(`/login?error=${encodeURIComponent(code)}`, 2000);
    };

    (async () => {
      const error = searchParams.get("error");
      if (error) {
        fail(
          normalizeErrorCode(error),
          "Authentication was denied or failed. Redirecting to login...",
        );
        return;
      }

      const code = searchParams.get("code");
      if (!code) {
        fail(
          "google_missing_code",
          "Invalid callback — missing sign-in code. Redirecting to login...",
        );
        return;
      }

      try {
        const user = await authApi.completeGoogleOAuth(code);
        if (cancelled) return;
        // Set store state directly rather than writing to localStorage and
        // asking hydrate() to read it back — that round trip is what the
        // redirect loop used to race against.
        setSession(user);
        setStatus("success");
        redirectTo("/dashboard", 800);
      } catch (err) {
        if (cancelled) return;
        console.error("Google OAuth completion failed:", err);
        fail(
          "google_completion_failed",
          "Authentication failed. Redirecting to login...",
        );
      }
    })();

    return () => {
      cancelled = true;
      for (const timer of timers) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4">
      <div className="flex flex-col items-center gap-4 text-center">
        {status === "loading" && (
          <>
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
            <h1 className="text-xl font-semibold text-slate-800">
              Signing you in with Google…
            </h1>
            <p className="text-sm text-slate-500">Just a moment</p>
          </>
        )}

        {status === "success" && (
          <>
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-green-100">
              <ShieldCheck className="h-8 w-8 text-green-600" />
            </div>
            <h1 className="text-xl font-semibold text-slate-800">
              Signed in successfully!
            </h1>
            <p className="text-sm text-slate-500">Redirecting to dashboard…</p>
          </>
        )}

        {status === "error" && (
          <>
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-red-100">
              <XCircle className="h-8 w-8 text-red-600" />
            </div>
            <h1 className="text-xl font-semibold text-slate-800">
              Sign-in failed
            </h1>
            <p className="text-sm text-slate-500">{errorMessage}</p>
          </>
        )}
      </div>
    </div>
  );
}
