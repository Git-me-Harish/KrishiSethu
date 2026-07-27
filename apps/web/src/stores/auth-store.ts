/**
 * Auth store — client-side authentication state.
 *
 * Uses Zustand for lightweight state management. The store is hydrated
 * from localStorage on first client-side render (in AuthProvider).
 *
 * Components subscribe via:
 *   const { user, isAuthenticated } = useAuthStore();
 */

import { create } from "zustand";
import { authApi, tokenStorage, type UserPublic } from "@/lib/api/client";

interface AuthState {
  user: UserPublic | null;
  isAuthenticated: boolean;
  /** True while the initial hydration from storage + /me is in flight. */
  isLoading: boolean;
  /** True while a user-initiated login/logout request is in flight. */
  isSubmitting: boolean;
  error: string | null;

  // Actions
  hydrate: () => Promise<void>;
  setSession: (user: UserPublic) => void;
  loginWithOtp: (phone: string, otp: string, fullName?: string) => Promise<void>;
  loginWithPassword: (phoneOrEmail: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
  refreshUser: () => Promise<void>;
  clearError: () => void;
}

/** Did this request fail because the server rejected our credentials? */
function isUnauthorized(err: unknown): boolean {
  return (err as { status?: number } | null)?.status === 401;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  // Start in loading state so route guards don't redirect before hydrate() runs
  isLoading: true,
  isSubmitting: false,
  error: null,

  /**
   * Restore the session from storage, then confirm it against the server.
   *
   * hydrate() MUST NOT clear storage as a side effect. It used to: seeing no
   * cached user object it called tokenStorage.clear(), which raced against
   * the OAuth callback. React flushes child effects before parent effects, so
   * on /auth/callback the callback page wrote its tokens, AuthProvider's
   * mount effect then ran hydrate(), found no user (the /me call had not
   * returned yet) and deleted the tokens that had just been written — the
   * user landed back on /login, forever.
   *
   * "Tokens present, user missing" is now treated as *still hydrating*, and
   * storage is cleared only when the server explicitly answers 401.
   */
  hydrate: async () => {
    if (!tokenStorage.hasTokens()) {
      set({ user: null, isAuthenticated: false, isLoading: false });
      return;
    }

    // Optimistically restore the cached user so guarded pages can render
    // immediately instead of flashing a spinner on every navigation.
    const cached = tokenStorage.getUser();
    if (cached) {
      set({ user: cached, isAuthenticated: true });
    }

    try {
      const user = await authApi.getMe();
      tokenStorage.setUser(user);
      set({ user, isAuthenticated: true, isLoading: false });
    } catch (err) {
      if (isUnauthorized(err)) {
        // The server has spoken: these tokens are dead.
        tokenStorage.clear();
        set({ user: null, isAuthenticated: false, isLoading: false });
        return;
      }
      // Network blip or server outage — keep the tokens and whatever we
      // restored from cache. Throwing the session away here would log people
      // out every time the API hiccups.
      set({ isLoading: false });
    }
  },

  /**
   * Adopt a session established elsewhere (e.g. the OAuth callback page),
   * without a round trip through localStorage and back.
   */
  setSession: (user) => {
    set({ user, isAuthenticated: true, isLoading: false, error: null });
  },

  loginWithOtp: async (phone, otp, fullName) => {
    set({ isSubmitting: true, error: null });
    try {
      const response = await authApi.verifyOtp({
        phone,
        otp,
        full_name: fullName,
      });
      set({
        user: response.user,
        isAuthenticated: true,
        isSubmitting: false,
        isLoading: false,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Login failed";
      set({ isSubmitting: false, error: message });
      throw err;
    }
  },

  loginWithPassword: async (phoneOrEmail, password) => {
    set({ isSubmitting: true, error: null });
    try {
      const response = await authApi.loginWithPassword(phoneOrEmail, password);
      set({
        user: response.user,
        isAuthenticated: true,
        isSubmitting: false,
        isLoading: false,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Login failed";
      set({ isSubmitting: false, error: message });
      throw err;
    }
  },

  logout: async () => {
    set({ isSubmitting: true });
    try {
      await authApi.logout();
    } finally {
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        isSubmitting: false,
        error: null,
      });
    }
  },

  logoutAll: async () => {
    set({ isSubmitting: true });
    try {
      await authApi.logoutAll();
    } finally {
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        isSubmitting: false,
        error: null,
      });
    }
  },

  refreshUser: async () => {
    if (!tokenStorage.hasTokens()) return;
    try {
      const user = await authApi.getMe();
      tokenStorage.setUser(user);
      set({ user, isAuthenticated: true });
    } catch {
      // Token might be expired — let the api client handle refresh
    }
  },

  clearError: () => set({ error: null }),
}));
