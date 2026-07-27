"use client";

import { useEffect, ReactNode } from "react";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";

/**
 * Auth provider — hydrates auth state from storage on mount.
 *
 * Wrap the application with this provider (in layout.tsx) so that auth
 * state is available throughout the app.
 *
 * Two deliberate details:
 *
 * 1. Hydration is skipped entirely on /auth/callback. That page establishes
 *    the session itself, and React runs child effects before parent effects —
 *    so this provider's mount effect fires while the callback's exchange is
 *    still in flight. hydrate() no longer destroys anything in that window,
 *    but there is still no reason to race a /me call against a page whose
 *    whole job is to produce the very session we would be fetching.
 *
 * 2. hydrate() alone; the old code also called refreshUser() immediately
 *    after, firing two concurrent /me requests on every page load. hydrate()
 *    now performs the server confirmation itself.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const hydrate = useAuthStore((s) => s.hydrate);
  const pathname = usePathname();
  const isOAuthCallback = pathname?.startsWith("/auth/callback") ?? false;

  useEffect(() => {
    if (isOAuthCallback) return;
    void hydrate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <>{children}</>;
}
