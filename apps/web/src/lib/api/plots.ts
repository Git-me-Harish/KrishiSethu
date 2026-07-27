import { apiFetch } from "./client";
import type { PlotListItem, PlotListResponse, PlotResponse, PlotStatsResponse } from "./types";

export const plotApi = {
  async listMine(limit = 20, offset = 0): Promise<PlotListResponse> {
    return apiFetch(`/plots`, { query: { limit, offset } });
  },
  async getStats(): Promise<PlotStatsResponse> {
    return apiFetch(`/plots/stats`);
  },
  async getById(id: string): Promise<PlotResponse> {
    return apiFetch(`/plots/${id}`);
  },
  async create(payload: { name: string; area_hec: number; crop_type?: string; soil_type?: string; boundary_geojson?: object }): Promise<PlotResponse> {
    return apiFetch(`/plots`, { method: "POST", body: JSON.stringify(payload) });
  },
};