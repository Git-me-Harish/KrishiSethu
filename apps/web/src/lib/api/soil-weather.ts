import { apiFetch } from "./client";
import type { SoilTestListResponse, WeatherAdvisory } from "./types";

export const soilApi = {
  async listTests(plotId: string): Promise<SoilTestListResponse> {
    return apiFetch(`/soil-weather/soil-tests`, { query: { plot_id: plotId } });
  },
  async getWeatherAdvisory(plotId: string): Promise<WeatherAdvisory> {
    return apiFetch(`/soil-weather/advisory`, { query: { plot_id: plotId } });
  },
};