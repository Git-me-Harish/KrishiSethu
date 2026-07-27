import { apiFetch } from "./client";
import type { GovtScheme, SchemeApplication, SchemeStats } from "./types";

export const schemesApi = {
  async listEligible(limit = 20, offset = 0): Promise<{ schemes: GovtScheme[]; total: number }> {
    return apiFetch(`/schemes/eligible`, { query: { limit, offset } });
  },
  async listApplications(limit = 20, offset = 0): Promise<{ applications: SchemeApplication[]; total: number }> {
    return apiFetch(`/schemes/applications`, { query: { limit, offset } });
  },
  async getStats(): Promise<SchemeStats> {
    return apiFetch(`/schemes/stats`);
  },
};