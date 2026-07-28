/**
 * NDVI (Normalized Difference Vegetation Index) API client.
 *
 * Mirrors the backend REST surface under /api/v1/plots/{id}/ndvi/* and
 * /api/v1/ndvi/anomalies/* — see apps/api/krishisetu/domains/ndvi/routes.py.
 *
 * Method names match the call-sites in:
 * - app/dashboard/ndvi/page.tsx  (getPlotSummary, refreshPlot, acknowledgeAnomaly)
 */

import { apiFetch } from "./client";
import type {
  NDVIAnomalyAlert,
  NDVIAnomalyListResponse,
  NDVIHistoryResponse,
  NDVIRefreshResponse,
  PlotNDVISummaryResponse,
} from "./types";

export const ndviApi = {
  async getPlotSummary(plotId: string): Promise<PlotNDVISummaryResponse> {
    return apiFetch<PlotNDVISummaryResponse>(`/plots/${plotId}/ndvi/summary`);
  },

  async getPlotHistory(
    plotId: string,
    limit = 12,
  ): Promise<NDVIHistoryResponse> {
    return apiFetch<NDVIHistoryResponse>(`/plots/${plotId}/ndvi/history`, {
      query: { limit },
    });
  },

  async refreshPlot(plotId: string): Promise<NDVIRefreshResponse> {
    return apiFetch<NDVIRefreshResponse>(`/plots/${plotId}/ndvi/refresh`, {
      method: "POST",
    });
  },

  async listPlotAnomalies(plotId: string): Promise<NDVIAnomalyListResponse> {
    return apiFetch<NDVIAnomalyListResponse>(`/plots/${plotId}/ndvi/anomalies`);
  },

  async acknowledgeAnomaly(
    alertId: string,
    resolutionNotes?: string,
  ): Promise<NDVIAnomalyAlert> {
    return apiFetch<NDVIAnomalyAlert>(`/ndvi/anomalies/${alertId}/ack`, {
      method: "PATCH",
      body: JSON.stringify({ resolution_notes: resolutionNotes ?? null }),
    });
  },
};

// Officer-only NDVI heatmap (officer role only)
export const officerNdviApi = {
  async getDistrictHeatmap(params?: {
    state?: string;
    days_back?: number;
  }): Promise<{
    state: string | null;
    districts: Array<{
      district: string;
      state: string;
      avg_ndvi: string | null;
      min_ndvi: string | null;
      max_ndvi: string | null;
      plot_count: number;
      healthy_plots: number;
      moderate_plots: number;
      sparse_plots: number;
      bare_plots: number;
      active_anomalies: number;
    }>;
    total_plots: number;
    avg_ndvi: string | null;
    generated_at: string;
  }> {
    return apiFetch(`/officer/ndvi/heatmap`, { query: params });
  },
};
