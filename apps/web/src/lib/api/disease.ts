import { apiFetch } from "./client";
import type {
  DiseaseFeedbackCreate,
  DiseaseFeedbackResponse,
  DiseaseReport,
  DiseaseReportListResponse,
  DiseaseReportStats,
  UploadUrlResponse,
} from "./types";

export const diseaseApi = {
  async listMyReports(page = 1, pageSize = 20): Promise<DiseaseReportListResponse> {
    return apiFetch<DiseaseReportListResponse>("/disease-reports", {
      query: { page, page_size: pageSize },
    });
  },
  async getStats(): Promise<DiseaseReportStats> {
    return apiFetch<DiseaseReportStats>("/disease-reports/stats");
  },
  async getReport(id: string): Promise<DiseaseReport> {
    return apiFetch<DiseaseReport>(`/disease-reports/${id}`);
  },
  async submitFeedback(
    reportId: string,
    payload: DiseaseFeedbackCreate,
  ): Promise<DiseaseFeedbackResponse> {
    return apiFetch<DiseaseFeedbackResponse>(`/disease-reports/${reportId}/feedback`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  async getUploadUrl(
    contentType: "image/jpeg" | "image/png" | "image/webp" = "image/jpeg",
  ): Promise<UploadUrlResponse> {
    return apiFetch<UploadUrlResponse>("/disease-reports/upload-url", {
      method: "POST",
      body: JSON.stringify({ content_type: contentType }),
    });
  },
  /**
   * Submit a disease report for an image already uploaded to the pre-signed
   * S3 URL from getUploadUrl(). There is no single-call multipart endpoint —
   * the backend only accepts a JSON body referencing the S3 image_key.
   */
  async createReport(payload: {
    plot_id?: string;
    crop_cycle_id?: string;
    image_key: string;
    image_content_type?: string;
    captured_at?: string;
    farmer_notes?: string;
  }): Promise<DiseaseReport> {
    return apiFetch<DiseaseReport>("/disease-reports", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
