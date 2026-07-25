"use client";

import { useEffect, ReactNode } from "react";
import { useAuthStore } from "@/stores/auth-store";

/**
 * Auth provider — hydrates auth state from localStorage on mount.
 *
 * Wrap the application with this provider (in layout.tsx) so that auth
 * state is available throughout the app.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const hydrate = useAuthStore((s) => s.hydrate);
  const refreshUser = useAuthStore((s) => s.refreshUser);

  useEffect(() => {
    hydrate();
    // If we have stored tokens, refresh user data from API
    // (ensures local state matches server state after a refresh)
    refreshUser();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <>{children}</>;
}
