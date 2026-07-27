import { apiFetch } from "./client";

/**
 * Schemes domain types — mirrors krishisetu/domains/schemes/schemas.py.
 * Exported from this module (not lib/api/types.ts) because that's where the
 * dashboard pages already import them from.
 */

export interface GovtScheme {
  id: string;
  code: string;
  name: string;
  name_hi: string | null;
  short_description: string;
  full_description: string;
  category: string;
  level: string;
  ministry: string | null;
  states: string[] | null;
  benefit_type: string | null;
  benefit_amount: number | null;
  benefit_frequency: string | null;
  benefit_description: string | null;
  application_mode: string;
  documents_required: string[] | null;
  application_url: string | null;
  source_url: string | null;
  helpline_number: string | null;
  is_featured: boolean;
  is_eligible: boolean | null;
  eligibility_reasons: string[] | null;
  has_applied: boolean;
  application_status: string | null;
}

export interface SchemeListResponse {
  schemes: GovtScheme[];
  total: number;
  eligible_count: number | null;
}

export interface SchemeApplication {
  id: string;
  application_number: string;
  scheme_id: string;
  farmer_id: string;
  status: string;
  submitted_data: Record<string, unknown>;
  eligibility_result: Record<string, unknown> | null;
  submitted_documents: string[] | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_notes: string | null;
  rejection_reason: string | null;
  benefit_disbursed_at: string | null;
  benefit_reference: string | null;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
  scheme_name: string | null;
  scheme_code: string | null;
}

export interface SchemeApplicationListResponse {
  applications: SchemeApplication[];
  total: number;
}

export interface SchemeStats {
  total_schemes_available: number;
  eligible_schemes: number;
  total_applications: number;
  pending_applications: number;
  approved_applications: number;
}

export const schemesApi = {
  async listSchemes(params: {
    category?: string;
    state?: string;
    page?: number;
    page_size?: number;
  } = {}): Promise<SchemeListResponse> {
    return apiFetch(`/schemes`, { query: params });
  },
  async getScheme(code: string): Promise<GovtScheme> {
    return apiFetch(`/schemes/${code}`);
  },
  async getStats(): Promise<SchemeStats> {
    return apiFetch(`/schemes/stats`);
  },
  async listMyApplications(status?: string): Promise<SchemeApplicationListResponse> {
    return apiFetch(`/schemes/applications`, { query: { status } });
  },
  async createApplication(
    schemeId: string,
    additionalData?: Record<string, unknown>,
  ): Promise<SchemeApplication> {
    return apiFetch(`/schemes/applications`, {
      method: "POST",
      body: JSON.stringify({ scheme_id: schemeId, additional_data: additionalData }),
    });
  },
  async submitApplication(
    appId: string,
    payload: { additional_data?: Record<string, unknown>; submitted_documents?: string[] } = {},
  ): Promise<SchemeApplication> {
    return apiFetch(`/schemes/applications/${appId}/submit`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  async withdrawApplication(appId: string): Promise<SchemeApplication> {
    return apiFetch(`/schemes/applications/${appId}/withdraw`, { method: "POST" });
  },
};
