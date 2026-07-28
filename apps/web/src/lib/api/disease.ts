/**
 * Disease identification API client.
 *
 * Mirrors the backend REST surface under /api/v1/disease-reports/* and
 * /api/v1/diseases/* — see apps/api/krishisetu/domains/disease/routes.py.
 *
 * Method names match the call-sites in:
 * - app/dashboard/disease/page.tsx       (listMyReports, getStats)
 * - app/dashboard/disease/[id]/page.tsx  (getReport, submitFeedback)
 *
 * Upload flow (T6 will add a /dashboard/disease/upload page that uses this):
 *   1. getUploadUrl(contentType)   →  { upload_url, image_key }
 *   2. PUT the image bytes to upload_url (direct to S3, no auth header)
 *   3. submitReport({ image_key, ... })  →  creates the report
 */

import { apiFetch, tokenStorage } from "./client";
import type {
  DiseaseFeedbackCreateRequest,
  DiseaseFeedbackResponse,
  DiseaseListResponse,
  DiseaseReport,
  DiseaseReportCreateRequest,
  DiseaseReportListResponse,
  DiseaseReportStats,
  DiseaseReportStatus,
  DiseaseResponse,
  UploadUrlRequest,
  UploadUrlResponse,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_PREFIX = "/api/v1";

export const diseaseApi = {
  // -----------------------------------------------------------------------
  // Stats (dashboard)
  // -----------------------------------------------------------------------

  /**
   * Get summary statistics for the current farmer's disease reports.
   * Backend: GET /disease-reports/stats
   */
  async getStats(): Promise<DiseaseReportStats> {
    return apiFetch<DiseaseReportStats>("/disease-reports/stats");
  },

  // -----------------------------------------------------------------------
  // Report submission flow (3 steps)
  // -----------------------------------------------------------------------

  /**
   * Step 1 of 3: Get a pre-signed S3 URL for uploading a disease photo.
   * The URL expires after 15 minutes. Max image size is 10MB.
   * Backend: POST /disease-reports/upload-url
   */
  async getUploadUrl(
    payload: UploadUrlRequest = { content_type: "image/jpeg" },
  ): Promise<UploadUrlResponse> {
    return apiFetch<UploadUrlResponse>("/disease-reports/upload-url", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async uploadImageToS3(
    uploadUrl: string,
    imageBlob: Blob,
    contentType: string = "image/jpeg",
  ): Promise<void> {
    const response = await fetch(uploadUrl, {
      method: "PUT",
      headers: { "Content-Type": contentType },
      body: imageBlob,
    });
    if (!response.ok) {
      throw new Error(
        `Image upload to S3 failed: ${response.status} ${response.statusText}`,
      );
    }
  },

  async uploadImage(
    imageBlob: Blob,
    contentType: "image/jpeg" | "image/png" | "image/webp" = "image/jpeg",
  ): Promise<string> {
    const { upload_url, image_key } = await this.getUploadUrl({ content_type: contentType });
    await this.uploadImageToS3(upload_url, imageBlob, contentType);
    return image_key;
  },

  async submitReport(
    payload: DiseaseReportCreateRequest,
  ): Promise<DiseaseReport> {
    return apiFetch<DiseaseReport>("/disease-reports", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Report listing & detail
  async listMyReports(params?: {
    status?: DiseaseReportStatus;
    page?: number;
    page_size?: number;
  }): Promise<DiseaseReportListResponse> {
    // Backwards-compat: the original call site used (page, limit) positional
    // args. If the first arg is a number, treat it as page.
    if (typeof params === "number") {
      params = { page: params, page_size: arguments[1] ?? 20 };
    }
    return apiFetch<DiseaseReportListResponse>("/disease-reports", {
      query: params,
    });
  },

  async getReport(reportId: string): Promise<DiseaseReport> {
    return apiFetch<DiseaseReport>(`/disease-reports/${reportId}`);
  },

  // Feedback (helps improve the model)
  async submitFeedback(
    reportId: string,
    payload: DiseaseFeedbackCreateRequest,
  ): Promise<DiseaseFeedbackResponse> {
    return apiFetch<DiseaseFeedbackResponse>(
      `/disease-reports/${reportId}/feedback`,
      { method: "POST", body: JSON.stringify(payload) },
    );
  },

  // Disease catalog (public — no auth required)
  async listDiseases(params?: {
    crop?: string;
    disease_type?: string;
    page?: number;
    page_size?: number;
  }): Promise<DiseaseListResponse> {
    return apiFetch<DiseaseListResponse>("/diseases", { query: params });
  },

  async getDisease(slug: string): Promise<DiseaseResponse> {
    return apiFetch<DiseaseResponse>(`/diseases/${slug}`);
  },
};

// Officer-only disease review API (agri_officer role only)
export const officerDiseaseApi = {
  async listReviewQueue(params?: {
    page?: number;
    page_size?: number;
  }): Promise<DiseaseReportListResponse> {
    return apiFetch<DiseaseReportListResponse>(
      "/officer/disease-reports/review-queue",
      { query: params },
    );
  },

  async reviewReport(
    reportId: string,
    payload: {
      diagnosis: string;
      disease_slug?: string;
    },
  ): Promise<DiseaseReport> {
    return apiFetch<DiseaseReport>(
      `/officer/disease-reports/${reportId}/review`,
      { method: "PATCH", body: JSON.stringify(payload) },
    );
  },
};

void tokenStorage;
void API_BASE_URL;
void API_PREFIX;
