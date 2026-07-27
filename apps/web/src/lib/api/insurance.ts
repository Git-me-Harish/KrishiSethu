import { apiFetch } from "./client";
import type { ClaimListResponse, InsurancePolicy, PolicyListResponse } from "./types";

export const insuranceApi = {
  async listPolicies(limit = 20, offset = 0): Promise<PolicyListResponse> {
    return apiFetch(`/insurance/policies`, { query: { limit, offset } });
  },
  async listClaims(policyId?: string, limit = 20, offset = 0): Promise<ClaimListResponse> {
    return apiFetch(`/insurance/claims`, { query: { policy_id: policyId, limit, offset } });
  },
  async getPolicy(id: string): Promise<InsurancePolicy> {
    return apiFetch(`/insurance/policies/${id}`);
  },
};