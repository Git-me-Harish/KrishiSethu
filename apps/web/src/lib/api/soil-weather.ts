/**
 * Soil & Weather API client.
 *
 * Mirrors the backend REST surface under:
 *   /api/v1/plots/{id}/soil-tests/*
 *   /api/v1/plots/{id}/weather/*
 *   /api/v1/weather/district/{district}/*
 * See apps/api/krishisetu/domains/soil_weather/routes.py.
 *
 * Method names match the call-sites in:
 * - app/dashboard/soil/page.tsx     (soilApi.listPlotTests, soilApi.createPlotTest)
 * - app/dashboard/weather/page.tsx  (weatherApi.getPlotSummary)
 *
 * FIX (T2): the previous version only exported `soilApi` — but the weather
 * page imports `weatherApi`, which didn't exist. This file now exports both.
 */

import { apiFetch } from "./client";
import type {
  CurrentWeather,
  ForecastResponse,
  PlotWeatherSummaryResponse,
  SoilTestCreateRequest,
  SoilTestListResponse,
  SoilTestResponse,
  WeatherAlertListResponse,
} from "./types";

// ---------------------------------------------------------------------------
// Soil tests (per-plot, farmer-facing)
// ---------------------------------------------------------------------------

export const soilApi = {
  /**
   * List all soil tests for a plot, most recent first.
   * Backend: GET /plots/{id}/soil-tests?page=&page_size=
   */
  async listPlotTests(
    plotId: string,
    params?: { page?: number; page_size?: number },
  ): Promise<SoilTestListResponse> {
    return apiFetch<SoilTestListResponse>(`/plots/${plotId}/soil-tests`, {
      query: params,
    });
  },

  /**
   * Add a manual soil test result for a plot (from a lab report).
   * The platform auto-generates fertilizer + amendment recommendations.
   * Backend: POST /plots/{id}/soil-tests
   */
  async createPlotTest(
    plotId: string,
    payload: SoilTestCreateRequest,
  ): Promise<SoilTestResponse> {
    return apiFetch<SoilTestResponse>(`/plots/${plotId}/soil-tests`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * Get a specific soil test by ID.
   * Backend: GET /plots/{id}/soil-tests/{test_id}
   * (Not currently exposed as a separate route — use listPlotTests and find by ID.)
   */
  // async getPlotTest(plotId: string, testId: string): Promise<SoilTestResponse> {
  //   return apiFetch<SoilTestResponse>(
  //     `/plots/${plotId}/soil-tests/${testId}`,
  //   );
  // },

  /**
   * Import soil test from the Soil Health Card portal (Phase 2 — in development).
   * Backend: POST /plots/{id}/soil-tests/import-shc
   */
  async importShc(plotId: string, shcId: string): Promise<SoilTestResponse> {
    return apiFetch<SoilTestResponse>(`/plots/${plotId}/soil-tests/import-shc`, {
      method: "POST",
      body: JSON.stringify({ shc_id: shcId }),
    });
  },
};

// Weather (per-plot, farmer-facing)
export const weatherApi = {
  async getPlotSummary(plotId: string): Promise<PlotWeatherSummaryResponse> {
    return apiFetch<PlotWeatherSummaryResponse>(`/plots/${plotId}/weather/summary`);
  },

  async getPlotCurrent(plotId: string): Promise<CurrentWeather> {
    return apiFetch<CurrentWeather>(`/plots/${plotId}/weather/current`);
  },

  async getPlotForecast(plotId: string): Promise<ForecastResponse> {
    return apiFetch<ForecastResponse>(`/plots/${plotId}/weather/forecast`);
  },

  async getPlotAlerts(plotId: string): Promise<WeatherAlertListResponse> {
    return apiFetch<WeatherAlertListResponse>(`/plots/${plotId}/weather/alerts`);
  },
};

// District-level weather (public — no auth required)
export const districtWeatherApi = {
  async getCurrent(district: string, state: string): Promise<CurrentWeather> {
    return apiFetch<CurrentWeather>(`/weather/district/${district}`, {
      query: { state },
    });
  },

  async getForecast(district: string, state: string): Promise<ForecastResponse> {
    return apiFetch<ForecastResponse>(`/weather/district/${district}/forecast`, {
      query: { state },
    });
  },

  async getAlerts(district: string, state: string): Promise<WeatherAlertListResponse> {
    return apiFetch<WeatherAlertListResponse>(`/weather/district/${district}/alerts`, {
      query: { state },
    });
  },
};
