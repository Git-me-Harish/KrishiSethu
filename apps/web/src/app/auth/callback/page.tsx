"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, ShieldCheck, XCircle } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { authApi } from "@/lib/api/client";

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
 * 1. Reads access_token + refresh_token from URL params
 * 2. Stores them via authApi.completeGoogleOAuth (stores + fetches /me)
 * 3. Hydrates the auth store
 * 4. Redirects to /dashboard
 *
 * On any failure it shows an error and redirects to /login.
 */
export default function AuthCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { hydrate } = useAuthStore();

  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState<string>("");

  useEffect(() => {
    const accessToken = searchParams.get("access_token");
    const refreshToken = searchParams.get("refresh_token");

    if (!accessToken || !refreshToken) {
      setStatus("error");
      setErrorMessage("Invalid callback — missing tokens. Redirecting to login...");
      const timeout = setTimeout(() => router.replace("/login?error=google_missing_tokens"), 2500);
      return () => clearTimeout(timeout);
    }

    authApi
      .completeGoogleOAuth(accessToken, refreshToken)
      .then(() => {
        hydrate();
        setStatus("success");
        // Brief success flash before redirect
        const timeout = setTimeout(() => router.replace("/dashboard"), 800);
        return () => clearTimeout(timeout);
      })
      .catch((err: Error) => {
        console.error("Google OAuth completion failed:", err);
        setStatus("error");
        setErrorMessage("Authentication failed. Redirecting to login...");
        const timeout = setTimeout(() => router.replace("/login?error=google_completion_failed"), 2500);
        return () => clearTimeout(timeout);
      });
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