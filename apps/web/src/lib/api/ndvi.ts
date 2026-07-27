import { apiFetch } from "./client";
import type { NDVIObservation, NDVIAnomalyAlert } from "./types";

export const ndviApi = {
  async listObservations(plotId: string, limit = 20, offset = 0): Promise<{ observations: NDVIObservation[]; total: number }> {
    return apiFetch(`/ndvi/observations`, { query: { plot_id: plotId, limit, offset } });
  },
  async listAlerts(plotId?: string, acknowledged?: boolean): Promise<NDVIAnomalyAlert[]> {
    return apiFetch("/ndvi/alerts", { query: { plot_id: plotId, acknowledged } });
  },
};