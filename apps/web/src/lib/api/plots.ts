import { apiFetch } from "./client";
import type {
  CropCycleCreatePayload,
  CropCycleResponse,
  CropCycleUpdatePayload,
  CropListResponse,
  PlotCreatePayload,
  PlotListResponse,
  PlotResponse,
  PlotStatsResponse,
} from "./types";

export const plotApi = {
  async listMyPlots(page = 1, pageSize = 20): Promise<PlotListResponse> {
    return apiFetch(`/plots`, { query: { page, page_size: pageSize } });
  },
  async getPlotStats(): Promise<PlotStatsResponse> {
    return apiFetch(`/plots/stats`);
  },
  async getPlot(id: string): Promise<PlotResponse> {
    return apiFetch(`/plots/${id}`);
  },
  async createPlot(payload: PlotCreatePayload): Promise<PlotResponse> {
    return apiFetch(`/plots`, { method: "POST", body: JSON.stringify(payload) });
  },
  async deletePlot(id: string): Promise<{ message: string }> {
    return apiFetch(`/plots/${id}`, { method: "DELETE" });
  },
  async listCrops(): Promise<CropListResponse> {
    return apiFetch(`/crops`);
  },
  async listCropCycles(plotId: string): Promise<CropCycleResponse[]> {
    return apiFetch(`/plots/${plotId}/crops`);
  },
  async createCropCycle(
    plotId: string,
    payload: CropCycleCreatePayload,
  ): Promise<CropCycleResponse> {
    return apiFetch(`/plots/${plotId}/crops`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  async updateCropCycle(
    cycleId: string,
    payload: CropCycleUpdatePayload,
  ): Promise<CropCycleResponse> {
    return apiFetch(`/crop-cycles/${cycleId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
};
