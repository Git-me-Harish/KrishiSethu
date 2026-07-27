/**
 * API client — single fetch wrapper used by all domain API modules.
 *
 * - Reads the base URL from NEXT_PUBLIC_API_URL (defaults to localhost:8000)
 * - Injects the JWT bearer token from tokenStorage on every request
 * - Handles 401 by attempting a single token refresh, then retries
 * - Parses JSON error envelopes into Error instances with helpful messages
 * - Forwards the X-Request-ID header when present (set by the API on responses)
 *
 * FIX: All `import type` statements moved to the top of the file.
 * The original had them scattered mid-file (after authApi, privacyApi etc.),
 * which caused Next.js 14's next-flight-client-entry-loader to fail during
 * RSC module graph analysis, producing the webpack
 * "Cannot read properties of undefined (reading 'call')" crash on every page.
 */

// ---------------------------------------------------------------------------
// All imports at the top — required for Next.js 14 RSC module graph analysis
// ---------------------------------------------------------------------------
import type { ApiError, TokenPair, UserPublic } from "./types";
export type { UserPublic };
import type { ConsentRecord, ConsentStatusResponse } from "./types";
import type {
  DataSubjectRequest,
  DSRType,
  Grievance,
  GrievanceStatus,
  DSRStatus,
} from "./types";
import type { AuditLogListResponse, AuditStatsResponse } from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_PREFIX = "/api/v1";

const ACCESS_TOKEN_KEY = "krishisetu_access_token";
const REFRESH_TOKEN_KEY = "krishisetu_refresh_token";
const USER_KEY = "krishisetu_user";

// ---------------------------------------------------------------------------
// Token storage (localStorage, SSR-safe)
// ---------------------------------------------------------------------------

export const tokenStorage = {
  getAccessToken(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(ACCESS_TOKEN_KEY);
  },
  getRefreshToken(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  },
  getUser(): UserPublic | null {
    if (typeof window === "undefined") return null;
    const raw = window.localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as UserPublic;
    } catch {
      return null;
    }
  },
  setTokens(accessToken: string, refreshToken: string): void {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  },
  setUser(user: UserPublic): void {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  hasTokens(): boolean {
    return !!this.getAccessToken() && !!this.getRefreshToken();
  },
  clear(): void {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  },
};

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

interface FetchOptions extends RequestInit {
  /** Skip auth header (for login endpoints) */
  skipAuth?: boolean;
  /** Query parameters */
  query?: Record<string, string | number | boolean | undefined | null>;
}

async function apiFetch<T>(
  path: string,
  options: FetchOptions = {},
): Promise<T> {
  const { skipAuth, query, headers, ...rest } = options;

  const url = new URL(`${API_PREFIX}${path}`, API_BASE_URL);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null) {
        url.searchParams.set(k, String(v));
      }
    }
  }

  const finalHeaders = new Headers(headers);
  if (!finalHeaders.has("Content-Type") && rest.body) {
    finalHeaders.set("Content-Type", "application/json");
  }
  if (!skipAuth) {
    const token = tokenStorage.getAccessToken();
    if (token) {
      finalHeaders.set("Authorization", `Bearer ${token}`);
    }
  }

  let response = await fetch(url.toString(), {
    ...rest,
    headers: finalHeaders,
    credentials: "include",
  });

  // On 401, attempt a single refresh + retry
  if (response.status === 401 && !skipAuth) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      const token = tokenStorage.getAccessToken();
      if (token) {
        finalHeaders.set("Authorization", `Bearer ${token}`);
      }
      response = await fetch(url.toString(), {
        ...rest,
        headers: finalHeaders,
        credentials: "include",
      });
    }
  }

  if (!response.ok) {
    let errBody: ApiError | null = null;
    try {
      errBody = (await response.json()) as ApiError;
    } catch {
      // non-JSON error response
    }
    const message = errBody?.error?.message ?? `Request failed: ${response.status}`;
    const err = new Error(message) as Error & { code?: string; status?: number };
    err.code = errBody?.error?.code;
    err.status = response.status;
    throw err;
  }

  if (response.status === 204) {
    return null as T;
  }
  return (await response.json()) as T;
}

let refreshPromise: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const refreshToken = tokenStorage.getRefreshToken();
    if (!refreshToken) return false;
    try {
      const data = await apiFetch<TokenPair>("/auth/refresh", {
        method: "POST",
        skipAuth: true,
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      tokenStorage.setTokens(data.access_token, data.refresh_token);
      tokenStorage.setUser(data.user);
      return true;
    } catch {
      tokenStorage.clear();
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

// ---------------------------------------------------------------------------
// Auth API
// ---------------------------------------------------------------------------

/**
 * FIX: sendOtp return type corrected to match backend SendOTPResponse schema.
 * Original declared { message, otp_sent } which don't exist on the response.
 */
export interface SendOtpResponse {
  phone: string;
  purpose: string;
  ttl_seconds: number;
  cooldown_seconds: number;
  max_attempts: number;
  debug_otp?: string | null;
}

export const authApi = {
  async sendOtp(
    phone: string,
    purpose: "login" | "signup" | "phone_change" = "login",
  ): Promise<SendOtpResponse> {
    return apiFetch<SendOtpResponse>("/auth/send-otp", {
      method: "POST",
      skipAuth: true,
      body: JSON.stringify({ phone, purpose }),
    });
  },

  async verifyOtp(payload: {
    phone: string;
    otp: string;
    full_name?: string;
  }): Promise<TokenPair> {
    const data = await apiFetch<TokenPair>("/auth/verify-otp", {
      method: "POST",
      skipAuth: true,
      body: JSON.stringify(payload),
    });
    tokenStorage.setTokens(data.access_token, data.refresh_token);
    tokenStorage.setUser(data.user);
    return data;
  },

  async loginWithPassword(
    phoneOrEmail: string,
    password: string,
  ): Promise<TokenPair> {
    const data = await apiFetch<TokenPair>("/auth/login-password", {
      method: "POST",
      skipAuth: true,
      body: JSON.stringify({ phone_or_email: phoneOrEmail, password }),
    });
    tokenStorage.setTokens(data.access_token, data.refresh_token);
    tokenStorage.setUser(data.user);
    return data;
  },

  /**
   * FIX: now sends refresh_token in the request body.
   * Original sent no body — backend LogoutRequest requires refresh_token,
   * so the server returned 422 and never revoked the token.
   */
  async logout(): Promise<void> {
    const refreshToken = tokenStorage.getRefreshToken();
    try {
      if (refreshToken) {
        await apiFetch("/auth/logout", {
          method: "POST",
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
      }
    } catch {
      // Best-effort — always clear local state even if server call fails
    } finally {
      tokenStorage.clear();
    }
  },

  async logoutAll(): Promise<void> {
    try {
      await apiFetch("/auth/logout-all", { method: "POST" });
    } finally {
      tokenStorage.clear();
    }
  },

  async getMe(): Promise<UserPublic> {
    return apiFetch<UserPublic>("/me");
  },

  async updateMe(payload: Partial<UserPublic>): Promise<UserPublic> {
    const data = await apiFetch<UserPublic>("/me", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    tokenStorage.setUser(data);
    return data;
  },

  /**
   * Complete the Google OAuth flow from the frontend callback page.
   * Called by /app/auth/callback/page.tsx after the backend redirects
   * with access_token + refresh_token in URL params.
   */
  async completeGoogleOAuth(
    accessToken: string,
    refreshToken: string,
  ): Promise<UserPublic> {
    tokenStorage.setTokens(accessToken, refreshToken);
    const user = await apiFetch<UserPublic>("/me");
    tokenStorage.setUser(user);
    return user;
  },
};

// ---------------------------------------------------------------------------
// Consent API (Phase F)
// ---------------------------------------------------------------------------

export const consentApi = {
  async getStatus(): Promise<ConsentStatusResponse> {
    return apiFetch<ConsentStatusResponse>("/consent");
  },
  async getHistory(): Promise<ConsentRecord[]> {
    return apiFetch<ConsentRecord[]>("/consent/history");
  },
  async grant(purposes: ConsentStatusResponse["granted"], noticeVersion = "2026.07.01", language = "en"): Promise<ConsentRecord[]> {
    return apiFetch<ConsentRecord[]>("/consent/grant", {
      method: "POST",
      body: JSON.stringify({ purposes, notice_version: noticeVersion, language }),
    });
  },
  async withdraw(purposes: ConsentStatusResponse["granted"], reason?: string): Promise<ConsentRecord[]> {
    return apiFetch<ConsentRecord[]>("/consent/withdraw", {
      method: "POST",
      body: JSON.stringify({ purposes, reason }),
    });
  },
};

// ---------------------------------------------------------------------------
// Privacy / DSR / Grievances API (Phase F)
// ---------------------------------------------------------------------------

export const privacyApi = {
  async fileDsr(payload: {
    request_type: DSRType;
    description?: string;
    requested_changes?: Record<string, string>;
  }): Promise<DataSubjectRequest> {
    return apiFetch<DataSubjectRequest>("/privacy/dsr", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  async listDsrs(): Promise<DataSubjectRequest[]> {
    return apiFetch<DataSubjectRequest[]>("/privacy/dsr");
  },
  async getDsr(id: string): Promise<DataSubjectRequest> {
    return apiFetch<DataSubjectRequest>(`/privacy/dsr/${id}`);
  },
  async confirmErasure(reason?: string): Promise<{ status: string; message: string }> {
    return apiFetch("/privacy/erasure/confirm", {
      method: "POST",
      body: JSON.stringify({ confirm_phrase: "DELETE MY ACCOUNT", reason }),
    });
  },
  async fileGrievance(payload: {
    category: string;
    subject: string;
    description: string;
  }): Promise<Grievance> {
    return apiFetch<Grievance>("/privacy/grievances", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  async listGrievances(): Promise<Grievance[]> {
    return apiFetch<Grievance[]>("/privacy/grievances");
  },
  async getGrievance(id: string): Promise<Grievance> {
    return apiFetch<Grievance>(`/privacy/grievances/${id}`);
  },
  async officerListDsrs(status?: DSRStatus): Promise<DataSubjectRequest[]> {
    return apiFetch<DataSubjectRequest[]>("/privacy/officer/dsr", {
      query: { status: status ?? undefined },
    });
  },
  async officerListGrievances(status?: GrievanceStatus): Promise<Grievance[]> {
    return apiFetch<Grievance[]>("/privacy/officer/grievances", {
      query: { status: status ?? undefined },
    });
  },
};

// ---------------------------------------------------------------------------
// Audit API (Phase F — admin only)
// ---------------------------------------------------------------------------

export const auditApi = {
  async searchLogs(params: {
    actor_id?: string;
    action?: string;
    resource_type?: string;
    resource_id?: string;
    start?: string;
    end?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<AuditLogListResponse> {
    return apiFetch<AuditLogListResponse>("/audit/logs", { query: params });
  },
  async getLog(id: string): Promise<AuditLogListResponse["logs"][number]> {
    return apiFetch(`/audit/logs/${id}`);
  },
  async stats(hours = 24): Promise<AuditStatsResponse> {
    return apiFetch<AuditStatsResponse>("/audit/stats", { query: { hours } });
  },
};

// ---------------------------------------------------------------------------
// Backwards-compat exports
// ---------------------------------------------------------------------------

export const apiClient = {
  get: <T>(path: string, query?: Record<string, unknown>) =>
    apiFetch<T>(path, { query: query as FetchOptions["query"] }),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => apiFetch<T>(path, { method: "DELETE" }),
};