import { apiFetch } from "./client";
import type {
  PlotWeatherSummary,
  SoilTestCreatePayload,
  SoilTestListResponse,
} from "./types";

export const soilApi = {
  async listPlotTests(plotId: string): Promise<SoilTestListResponse> {
    return apiFetch(`/plots/${plotId}/soil-tests`);
  },
  async createPlotTest(
    plotId: string,
    payload: SoilTestCreatePayload,
  ): Promise<SoilTestListResponse["tests"][number]> {
    return apiFetch(`/plots/${plotId}/soil-tests`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};

export const weatherApi = {
  async getPlotSummary(plotId: string): Promise<PlotWeatherSummary> {
    return apiFetch(`/plots/${plotId}/weather/summary`);
  },
};
