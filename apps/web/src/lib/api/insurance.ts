import { apiFetch } from "./client";
import type {
  ClaimCreatePayload,
  ClaimListResponse,
  InsuranceClaim,
  InsuranceProductListResponse,
  InsuranceStats,
  PolicyEnrollPayload,
  PolicyListResponse,
  PremiumEstimate,
  InsurancePolicy,
} from "./types";

export const insuranceApi = {
  async listPolicies(limit = 20, offset = 0): Promise<PolicyListResponse> {
    return apiFetch(`/insurance/policies`, { query: { limit, offset } });
  },
  async getPolicy(id: string): Promise<InsurancePolicy> {
    return apiFetch(`/insurance/policies/${id}`);
  },
  async getProductsForPlot(plotId: string, crop?: string): Promise<InsuranceProductListResponse> {
    return apiFetch(`/insurance/products/for-plot/${plotId}`, { query: { crop } });
  },
  async estimatePremium(productId: string, plotId: string): Promise<PremiumEstimate> {
    return apiFetch(`/insurance/products/${productId}/estimate`, { query: { plot_id: plotId } });
  },
  async enrollPolicy(payload: PolicyEnrollPayload): Promise<InsurancePolicy> {
    return apiFetch(`/insurance/policies`, { method: "POST", body: JSON.stringify(payload) });
  },
  async payPremium(policyId: string, paymentReference: string): Promise<InsurancePolicy> {
    return apiFetch(`/insurance/policies/${policyId}/pay`, {
      method: "POST",
      body: JSON.stringify({ payment_reference: paymentReference }),
    });
  },
  async getStats(): Promise<InsuranceStats> {
    return apiFetch(`/insurance/policies/stats`);
  },
  async listClaims(policyId?: string, limit = 20, offset = 0): Promise<ClaimListResponse> {
    return apiFetch(`/insurance/claims`, { query: { policy_id: policyId, limit, offset } });
  },
  async getClaim(id: string): Promise<InsuranceClaim> {
    return apiFetch(`/insurance/claims/${id}`);
  },
  async createClaim(payload: ClaimCreatePayload): Promise<InsuranceClaim> {
    return apiFetch(`/insurance/claims`, { method: "POST", body: JSON.stringify(payload) });
  },
  async submitClaim(
    claimId: string,
    bankAccountNumber: string,
    bankIfsc: string,
  ): Promise<InsuranceClaim> {
    return apiFetch(`/insurance/claims/${claimId}/submit`, {
      method: "POST",
      body: JSON.stringify({ bank_account_number: bankAccountNumber, bank_ifsc: bankIfsc }),
    });
  },
  async withdrawClaim(claimId: string): Promise<InsuranceClaim> {
    return apiFetch(`/insurance/claims/${claimId}/withdraw`, { method: "POST" });
  },
};
