/**
 * Plots API client.
 *
 * Mirrors the backend REST surface under /api/v1/plots, /api/v1/crop-cycles,
 * /api/v1/crops, and /api/v1/officer/plots — see
 * apps/api/krishisetu/domains/farmer/routes.py.
 *
 * Method names match the call-sites in:
 * - app/dashboard/plots/page.tsx           (listMyPlots, getPlotStats)
 * - app/dashboard/plots/register/page.tsx  (createPlot)
 * - app/dashboard/plots/[id]/page.tsx      (getPlot, listCropCycles, listCrops,
 *                                            createCropCycle, updateCropCycle,
 *                                            deletePlot)
 * - app/dashboard/ndvi/page.tsx            (listMyPlots)
 * - app/dashboard/soil/page.tsx            (listMyPlots)
 * - app/dashboard/weather/page.tsx         (listMyPlots)
 * - app/dashboard/insurance/policies/page.tsx (listMyPlots)
 */

import { apiFetch } from "./client";
import type {
  CropCycleCreateRequest,
  CropCycleResponse,
  CropCycleUpdateRequest,
  CropListResponse,
  PlotBoundaryUpdateRequest,
  PlotCreateRequest,
  PlotListResponse,
  PlotResponse,
  PlotStatsResponse,
  PlotUpdateRequest,
  VerificationStatus,
} from "./types";

export const plotApi = {

  // Plots CRUD
  async listMyPlots(page = 1, pageSize = 20): Promise<PlotListResponse> {
    return apiFetch<PlotListResponse>("/plots", {
      query: { page, page_size: pageSize },
    });
  },

  async getPlotStats(): Promise<PlotStatsResponse> {
    return apiFetch<PlotStatsResponse>("/plots/stats");
  },

  async getPlot(plotId: string): Promise<PlotResponse> {
    return apiFetch<PlotResponse>(`/plots/${plotId}`);
  },

  async createPlot(payload: PlotCreateRequest): Promise<PlotResponse> {
    return apiFetch<PlotResponse>("/plots", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async updatePlot(plotId: string, payload: PlotUpdateRequest): Promise<PlotResponse> {
    return apiFetch<PlotResponse>(`/plots/${plotId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  async updatePlotBoundary(
    plotId: string,
    payload: PlotBoundaryUpdateRequest,
  ): Promise<PlotResponse> {
    return apiFetch<PlotResponse>(`/plots/${plotId}/boundary`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  async deletePlot(plotId: string): Promise<{ message: string }> {
    return apiFetch<{ message: string }>(`/plots/${plotId}`, {
      method: "DELETE",
    });
  },

  // Crop cycles (sub-resource of plots)
  async listCropCycles(plotId: string): Promise<CropCycleResponse[]> {
    return apiFetch<CropCycleResponse[]>(`/plots/${plotId}/crops`);
  },

  async createCropCycle(
    plotId: string,
    payload: CropCycleCreateRequest,
  ): Promise<CropCycleResponse> {
    return apiFetch<CropCycleResponse>(`/plots/${plotId}/crops`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async updateCropCycle(
    cycleId: string,
    payload: CropCycleUpdateRequest,
  ): Promise<CropCycleResponse> {
    return apiFetch<CropCycleResponse>(`/crop-cycles/${cycleId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  // Crop master data (public — no auth required)
  async listCrops(params?: {
    category?: string;
    season?: "kharif" | "rabi" | "zaid";
  }): Promise<CropListResponse> {
    return apiFetch<CropListResponse>("/crops", { query: params });
  },

  // Officer routes (agri_officer role only)
  async officerListDistrictPlots(params: {
    district: string;
    state?: string;
    verification_status?: VerificationStatus;
    page?: number;
    page_size?: number;
  }): Promise<PlotListResponse> {
    return apiFetch<PlotListResponse>("/officer/plots", { query: params });
  },

  async officerVerifyPlot(
    plotId: string,
    payload: {
      status: "verified" | "rejected" | "resubmission_requested";
      notes?: string;
    },
  ): Promise<PlotResponse> {
    return apiFetch<PlotResponse>(`/officer/plots/${plotId}/verify`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
};
