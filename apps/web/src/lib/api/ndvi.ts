import { apiFetch } from "./client";
import type {
  NDVIAnomalyAlert,
  NDVIAnomalyListResponse,
  NDVIHistoryResponse,
  NDVIRefreshResponse,
  PlotNDVISummary,
} from "./types";

export const ndviApi = {
  async getPlotSummary(plotId: string): Promise<PlotNDVISummary> {
    return apiFetch(`/plots/${plotId}/ndvi/summary`);
  },
  async getHistory(plotId: string, limit = 12): Promise<NDVIHistoryResponse> {
    return apiFetch(`/plots/${plotId}/ndvi/history`, { query: { limit } });
  },
  async refreshPlot(plotId: string): Promise<NDVIRefreshResponse> {
    return apiFetch(`/plots/${plotId}/ndvi/refresh`, { method: "POST" });
  },
  async listAnomalies(plotId: string): Promise<NDVIAnomalyListResponse> {
    return apiFetch(`/plots/${plotId}/ndvi/anomalies`);
  },
  async acknowledgeAnomaly(alertId: string, resolutionNotes?: string): Promise<NDVIAnomalyAlert> {
    return apiFetch(`/ndvi/anomalies/${alertId}/ack`, {
      method: "PATCH",
      body: JSON.stringify({ resolution_notes: resolutionNotes }),
    });
  },
};
