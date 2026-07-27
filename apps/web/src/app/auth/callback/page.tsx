"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, ShieldCheck, XCircle } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { tokenStorage } from "@/lib/api/client";

/**
 * Google OAuth callback page.
 *
 * The backend's /auth/google/callback handler exchanges the Google
 * authorization code, issues KrishiSetu JWT tokens, and redirects here:
 *
 *   /auth/callback?access_token=...&refresh_token=...&expires_in=...
 *
 * On error (user denied consent, CSRF fail, etc.) the backend redirects:
 *
 *   /login?error=google_denied         — user cancelled
 *   /login?error=google_auth_failed    — auth/state failure
 *   /login?error=google_server_error   — unexpected server error
 *
 * This page:
 * 1. Reads access_token + refresh_token from URL query params
 * 2. Stores them in localStorage via tokenStorage
 * 3. Calls /me to fetch user and stores it
 * 4. Hydrates the auth store
 * 5. Redirects to /dashboard
 *
 * On any failure it shows an error and redirects to /login.
 */
export default function AuthCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { hydrate } = useAuthStore();
  const processed = useRef(false);

  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState<string>("");

  useEffect(() => {
    // Prevent double-execution in StrictMode
    if (processed.current) return;
    processed.current = true;

    (async () => {
      const error = searchParams.get("error");
      if (error) {
        setStatus("error");
        setErrorMessage("Authentication was denied or failed. Redirecting to login...");
        setTimeout(() => router.replace(`/login?error=${error}`), 2000);
        return;
      }

      const accessToken = searchParams.get("access_token");
      const refreshToken = searchParams.get("refresh_token");

      if (!accessToken || !refreshToken) {
        setStatus("error");
        setErrorMessage("Invalid callback — missing tokens. Redirecting to login...");
        setTimeout(() => router.replace("/login?error=google_missing_tokens"), 2000);
        return;
      }

      try {
        // Store tokens in localStorage
        tokenStorage.setTokens(accessToken, refreshToken);

        // Fetch user via /me and store it so hydrate() works immediately
        const { authApi } = await import("@/lib/api/client");
        try {
          const user = await authApi.getMe();
          tokenStorage.setUser(user);
        } catch {
          // /me can fail due to clock skew, but tokens are stored.
          // AuthProvider's hydrate() + refreshUser() will pick them up
          // when the dashboard page renders.
        }

        hydrate();
        setStatus("success");
        setTimeout(() => router.replace("/dashboard"), 800);
      } catch (err) {
        console.error("Google OAuth token storage failed:", err);
        setStatus("error");
        setErrorMessage("Failed to complete authentication. Redirecting to login...");
        setTimeout(() => router.replace("/login?error=google_storage_failed"), 2000);
      }
    })();
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