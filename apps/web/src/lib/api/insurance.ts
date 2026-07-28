/**
 * Insurance API client.
 *
 * Mirrors the backend REST surface under /api/v1/insurance/* — see
 * apps/api/krishisetu/domains/insurance/routes.py.
 *
 * Method names match the call-sites in:
 * - app/dashboard/insurance/page.tsx                    (getStats, listPolicies, listClaims)
 * - app/dashboard/insurance/policies/page.tsx           (getProductsForPlot, estimatePremium,
 *                                                         enrollPolicy)
 * - app/dashboard/insurance/policies/[id]/page.tsx      (getPolicy, listClaims, payPremium)
 * - app/dashboard/insurance/claims/file/page.tsx        (getPolicy, createClaim, submitClaim)
 * - app/dashboard/insurance/claims/[id]/page.tsx        (getClaim, withdrawClaim)
 */

import { apiFetch } from "./client";
import type {
  ClaimCreateRequest,
  ClaimListResponse,
  ClaimResponse,
  ClaimStatus,
  ClaimSubmitRequest,
  ClaimType,
  InsuranceProductListResponse,
  InsuranceProductPremiumEstimate,
  InsuranceStatsResponse,
  PolicyCreateRequest,
  PolicyListResponse,
  PolicyResponse,
  PolicyStatus,
} from "./types";

export const insuranceApi = {
  // Stats (dashboard)
  async getStats(): Promise<InsuranceStatsResponse> {
    return apiFetch<InsuranceStatsResponse>("/insurance/policies/stats");
  },

  // Products (public — no auth required for list/get)
  async listProducts(params?: {
    state?: string;
    crop?: string;
    season?: string;
    season_year?: number;
    product_type?: "pmfby" | "rwbcis" | "state_scheme" | "commercial";
    page?: number;
    page_size?: number;
  }): Promise<InsuranceProductListResponse> {
    return apiFetch<InsuranceProductListResponse>("/insurance/products", {
      query: params,
    });
  },

  async getProductsForPlot(
    plotId: string,
    cropSlug?: string,
  ): Promise<InsuranceProductListResponse> {
    return apiFetch<InsuranceProductListResponse>(
      `/insurance/products/for-plot/${plotId}`,
      { query: { crop: cropSlug } },
    );
  },

  async estimatePremium(
    productId: string,
    plotId: string,
  ): Promise<InsuranceProductPremiumEstimate> {
    return apiFetch<InsuranceProductPremiumEstimate>(
      `/insurance/products/${productId}/estimate`,
      { query: { plot_id: plotId } },
    );
  },

  // Policies (farmer-facing)
  async listPolicies(params?: {
    status?: PolicyStatus;
    page?: number;
    page_size?: number;
  }): Promise<PolicyListResponse> {
    return apiFetch<PolicyListResponse>("/insurance/policies", { query: params });
  },

  async getPolicy(policyId: string): Promise<PolicyResponse> {
    return apiFetch<PolicyResponse>(`/insurance/policies/${policyId}`);
  },


  async enrollPolicy(payload: PolicyCreateRequest): Promise<PolicyResponse> {
    return apiFetch<PolicyResponse>("/insurance/policies", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async payPremium(
    policyId: string,
    paymentReference: string,
  ): Promise<PolicyResponse> {
    return apiFetch<PolicyResponse>(`/insurance/policies/${policyId}/pay`, {
      method: "POST",
      body: JSON.stringify({ payment_reference: paymentReference }),
    });
  },

  // Claims (farmer-facing)
  async listClaims(params?: {
    status?: ClaimStatus;
    page?: number;
    page_size?: number;
  }): Promise<ClaimListResponse> {
    return apiFetch<ClaimListResponse>("/insurance/claims", { query: params });
  },

  async getClaim(claimId: string): Promise<ClaimResponse> {
    return apiFetch<ClaimResponse>(`/insurance/claims/${claimId}`);
  },

  async createClaim(payload: ClaimCreateRequest): Promise<ClaimResponse> {
    return apiFetch<ClaimResponse>("/insurance/claims", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async submitClaim(
    claimId: string,
    bankAccountNumber: string,
    bankIfsc: string,
  ): Promise<ClaimResponse> {
    const payload: ClaimSubmitRequest = {
      bank_account_number: bankAccountNumber,
      bank_ifsc: bankIfsc,
    };
    return apiFetch<ClaimResponse>(`/insurance/claims/${claimId}/submit`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async withdrawClaim(claimId: string): Promise<ClaimResponse> {
    return apiFetch<ClaimResponse>(`/insurance/claims/${claimId}/withdraw`, {
      method: "POST",
    });
  },
};

// Insurer-facing API (insurer role only)
export const insurerApi = {
  async listClaims(params?: {
    status?: ClaimStatus;
    page?: number;
    page_size?: number;
  }): Promise<{ claims: ClaimResponse[]; total: number }> {
    return apiFetch<{ claims: ClaimResponse[]; total: number }>("/insurer/claims", {
      query: params,
    });
  },

  async reviewClaim(
    claimId: string,
    payload: {
      action: "approve" | "reject" | "request_evidence";
      approved_amount?: string;
      review_notes?: string;
      rejection_reason?: string;
      evidence_request_notes?: string;
    },
  ): Promise<ClaimResponse> {
    return apiFetch<ClaimResponse>(`/insurer/claims/${claimId}/review`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
};

// Re-export claim/policy types for convenience
export type {
  ClaimCreateRequest,
  ClaimResponse,
  ClaimStatus,
  ClaimType,
  InsuranceStatsResponse,
  PolicyCreateRequest,
  PolicyResponse,
  PolicyStatus,
};
