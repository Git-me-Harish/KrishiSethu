/**
 * Government Schemes API client.
 *
 * Mirrors the backend REST surface under /api/v1/schemes/* and
 * /api/v1/officer/schemes/* — see apps/api/krishisetu/domains/schemes/routes.py.
 *
 * Method names match the call-sites in:
 * - app/dashboard/schemes/page.tsx  (listSchemes, getStats, listMyApplications,
 *                                    createApplication)
 */

import { apiFetch } from "./client";
import type {
  ApplicationStatus,
  SchemeApplicationCreateRequest,
  SchemeApplicationListResponse,
  SchemeApplicationResponse,
  SchemeListResponse,
  SchemeResponse,
  SchemeStatsResponse,
} from "./types";

export const schemesApi = {
  // Public scheme catalog (auth optional — eligibility evaluated if logged in)
  async listSchemes(params?: {
    category?: string;
    state?: string;
    page?: number;
    page_size?: number;
  }): Promise<SchemeListResponse> {
    return apiFetch<SchemeListResponse>("/schemes", { query: params });
  },

  async getScheme(schemeCode: string): Promise<SchemeResponse> {
    return apiFetch<SchemeResponse>(`/schemes/${schemeCode}`);
  },

  // Farmer stats + applications
  async getStats(): Promise<SchemeStatsResponse> {
    return apiFetch<SchemeStatsResponse>("/schemes/stats");
  },

  async listMyApplications(
    status?: ApplicationStatus,
  ): Promise<SchemeApplicationListResponse> {
    return apiFetch<SchemeApplicationListResponse>("/schemes/applications", {
      query: { status },
    });
  },

  async getApplication(applicationId: string): Promise<SchemeApplicationResponse> {
    return apiFetch<SchemeApplicationResponse>(
      `/schemes/applications/${applicationId}`,
    );
  },

  async createApplication(
    schemeIdOrPayload: string | SchemeApplicationCreateRequest,
  ): Promise<SchemeApplicationResponse> {
    const payload: SchemeApplicationCreateRequest =
      typeof schemeIdOrPayload === "string"
        ? { scheme_id: schemeIdOrPayload }
        : schemeIdOrPayload;
    return apiFetch<SchemeApplicationResponse>("/schemes/applications", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async submitApplication(
    applicationId: string,
    payload?: {
      additional_data?: Record<string, unknown>;
      submitted_documents?: string[];
    },
  ): Promise<SchemeApplicationResponse> {
    return apiFetch<SchemeApplicationResponse>(
      `/schemes/applications/${applicationId}/submit`,
      { method: "POST", body: JSON.stringify(payload ?? {}) },
    );
  },

  async withdrawApplication(
    applicationId: string,
  ): Promise<SchemeApplicationResponse> {
    return apiFetch<SchemeApplicationResponse>(
      `/schemes/applications/${applicationId}/withdraw`,
      { method: "POST" },
    );
  },
};

// Officer-only scheme review API (agri_officer role only)
export const officerSchemesApi = {

  async listApplications(params?: {
    status?: ApplicationStatus;
    page?: number;
    page_size?: number;
  }): Promise<SchemeApplicationListResponse> {
    return apiFetch<SchemeApplicationListResponse>("/officer/schemes/applications", {
      query: params,
    });
  },

  async reviewApplication(
    applicationId: string,
    payload: {
      action: "approve" | "reject" | "request_resubmission";
      review_notes?: string;
      rejection_reason?: string;
      benefit_reference?: string;
    },
  ): Promise<SchemeApplicationResponse> {
    return apiFetch<SchemeApplicationResponse>(
      `/officer/schemes/applications/${applicationId}/review`,
      { method: "PATCH", body: JSON.stringify(payload) },
    );
  },
};
