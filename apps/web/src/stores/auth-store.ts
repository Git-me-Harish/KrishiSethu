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
  isLoading: boolean;
  error: string | null;

  // Actions
  hydrate: () => void;
  loginWithOtp: (phone: string, otp: string, fullName?: string) => Promise<void>;
  loginWithPassword: (phoneOrEmail: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
  refreshUser: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  hydrate: () => {
    const user = tokenStorage.getUser();
    if (user && tokenStorage.hasTokens()) {
      set({ user, isAuthenticated: true });
    } else {
      tokenStorage.clear();
      set({ user: null, isAuthenticated: false });
    }
  },

  loginWithOtp: async (phone, otp, fullName) => {
    set({ isLoading: true, error: null });
    try {
      const response = await authApi.verifyOtp({
        phone,
        otp,
        full_name: fullName,
      });
      set({
        user: response.user,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Login failed";
      set({ isLoading: false, error: message });
      throw err;
    }
  },

  loginWithPassword: async (phoneOrEmail, password) => {
    set({ isLoading: true, error: null });
    try {
      const response = await authApi.loginWithPassword(phoneOrEmail, password);
      set({
        user: response.user,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Login failed";
      set({ isLoading: false, error: message });
      throw err;
    }
  },

  logout: async () => {
    set({ isLoading: true });
    try {
      await authApi.logout();
    } finally {
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
      });
    }
  },

  logoutAll: async () => {
    set({ isLoading: true });
    try {
      await authApi.logoutAll();
    } finally {
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
      });
    }
  },

  refreshUser: async () => {
    if (!tokenStorage.hasTokens()) return;
    try {
      const user = await authApi.getMe();
      set({ user, isAuthenticated: true });
    } catch {
      // Token might be expired — let the api client handle refresh
    }
  },

  clearError: () => set({ error: null }),
}));
