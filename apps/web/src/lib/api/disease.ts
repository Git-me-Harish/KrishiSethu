import { apiFetch } from "./client";
import type {
  DiseaseReport,
  DiseaseReportListResponse,
  DiseaseReportStats,
  DiseasePrediction,
} from "./types";

export const diseaseApi = {
  async listMyReports(page = 1, limit = 20): Promise<DiseaseReportListResponse> {
    return apiFetch<DiseaseReportListResponse>("/disease/reports", {
      query: { page, limit },
    });
  },
  async getStats(): Promise<DiseaseReportStats> {
    return apiFetch<DiseaseReportStats>("/disease/stats");
  },
  async getReport(id: string): Promise<DiseaseReport> {
    return apiFetch<DiseaseReport>(`/disease/reports/${id}`);
  },
  async uploadImage(formData: FormData): Promise<{ report_id: string }> {
    // Routed through apiFetch so the request gets the /api/v1 prefix, the
    // bearer token from tokenStorage, and the 401 refresh-and-retry.
    // No Content-Type is set here — fetch generates the multipart boundary.
    return apiFetch<{ report_id: string }>("/disease/reports", {
      method: "POST",
      body: formData,
    });
  },
};