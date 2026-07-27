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
    const url = new URL("/disease/reports", process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");
    const token = typeof window !== "undefined" ? window.localStorage.getItem("krishisetu_access_token") : null;
    const response = await fetch(url.toString(), {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: formData,
    });
    if (!response.ok) throw new Error("Upload failed");
    return response.json();
  },
};