"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  CloudRain,
  Droplets,
  Wind,
  Thermometer,
  Eye,
  Sun,
  Sunrise,
  Sunset,
  AlertTriangle,
  Calendar,
  Loader2,
  Sprout,
  MapPin,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { weatherApi } from "@/lib/api/soil-weather";
import { plotApi } from "@/lib/api/plots";
import type {
  CurrentWeather,
  DailyForecast,
  PlotWeatherSummary,
  WeatherAlert,
  PlotListResponse,
} from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatDate, formatDateTime } from "@/lib/utils";

const WEATHER_ICONS: Record<string, string> = {
  Clear: "☀️",
  Clouds: "☁️",
  Rain: "🌧️",
  Thunderstorm: "⛈️",
  Drizzle: "🌦️",
  Snow: "❄️",
  Mist: "🌫️",
  Fog: "🌫️",
  Haze: "🌫️",
};

const ALERT_SEVERITY_COLORS = {
  info: "bg-blue-50 text-blue-700 border-blue-200",
  warning: "bg-amber-50 text-amber-700 border-amber-200",
  severe: "bg-orange-50 text-orange-700 border-orange-200",
  critical: "bg-red-50 text-red-700 border-red-200",
} as const;

export default function WeatherPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const [plots, setPlots] = useState<PlotListResponse | null>(null);
  const [selectedPlotId, setSelectedPlotId] = useState<string | null>(null);
  const [summary, setSummary] = useState<PlotWeatherSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated) return;
    loadPlots();
  }, [isAuthenticated]);

  async function loadPlots() {
    try {
      const plotsResp = await plotApi.listMyPlots(1, 100);
      setPlots(plotsResp);
      if (plotsResp.plots.length > 0) {
        setSelectedPlotId(plotsResp.plots[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load plots");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!selectedPlotId) return;
    loadWeather();
  }, [selectedPlotId]);

  async function loadWeather() {
    if (!selectedPlotId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await weatherApi.getPlotSummary(selectedPlotId);
      setSummary(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load weather");
    } finally {
      setIsLoading(false);
    }
  }

  if (authLoading || !isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <Header />

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-6">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-primary"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to dashboard
          </Link>
        </div>

        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Weather Intelligence</h1>
            <p className="text-sm text-slate-600">
              Current conditions, 7-day forecast, and extreme weather alerts for your plots
            </p>
          </div>
        </div>

        {/* Plot selector */}
        {plots && plots.plots.length > 0 && (
          <Card className="mb-6">
            <CardContent className="p-4">
              <div className="flex flex-wrap items-center gap-3">
                <MapPin className="h-5 w-5 text-primary" />
                <select
                  value={selectedPlotId || ""}
                  onChange={(e) => setSelectedPlotId(e.target.value)}
                  className="flex h-10 flex-1 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  {plots.plots.map((plot) => (
                    <option key={plot.id} value={plot.id}>
                      {plot.nickname || `Plot ${plot.survey_number}`} — {plot.village}, {plot.district}
                    </option>
                  ))}
                </select>
                <Button variant="ghost" size="sm" onClick={loadWeather}>
                  Refresh
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {plots && plots.plots.length === 0 && (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <MapPin className="h-12 w-12 text-slate-300" />
              <p className="mt-3 text-sm font-medium text-slate-900">
                No plots registered
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Register a plot to access plot-specific weather data and alerts.
              </p>
              <Button
                onClick={() => router.push("/dashboard/plots/register")}
                className="mt-4"
              >
                Register a Plot
              </Button>
            </CardContent>
          </Card>
        )}

        {error && (
          <Card className="mb-6 border-red-200">
            <CardContent className="p-4">
              <p className="text-sm text-red-600">{error}</p>
              <Button variant="ghost" size="sm" onClick={loadWeather} className="mt-2">
                Retry
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Weather summary */}
        {summary && (
          <>
            {/* Active alerts */}
            {summary.active_alerts.length > 0 && (
              <div className="mb-6 space-y-3">
                {summary.active_alerts.map((alert) => (
                  <AlertCard key={alert.id} alert={alert} />
                ))}
              </div>
            )}

            {/* Current weather */}
            <Card className="mb-6">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <CloudRain className="h-5 w-5 text-primary" />
                  Current Conditions
                </CardTitle>
                <CardDescription>
                  {summary.district}, {summary.state} · Updated{" "}
                  {formatDateTime(summary.current.observed_at)}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-6 lg:grid-cols-3">
                  {/* Main temp */}
                  <div className="flex items-center gap-4">
                    <div className="text-6xl">
                      {WEATHER_ICONS[summary.current.weather_main] || "🌡️"}
                    </div>
                    <div>
                      <div className="text-5xl font-bold text-slate-900">
                        {Number(summary.current.temperature_c).toFixed(0)}°C
                      </div>
                      <div className="text-sm text-slate-600 capitalize">
                        {summary.current.weather_description}
                      </div>
                      <div className="text-xs text-slate-500">
                        Feels like {Number(summary.current.feels_like_c).toFixed(0)}°C
                      </div>
                    </div>
                  </div>

                  {/* Min/Max */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm">
                      <Thermometer className="h-4 w-4 text-red-500" />
                      <span className="text-slate-600">High:</span>
                      <span className="font-medium text-slate-900">
                        {Number(summary.current.temp_max_c).toFixed(0)}°C
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-sm">
                      <Thermometer className="h-4 w-4 text-blue-500" />
                      <span className="text-slate-600">Low:</span>
                      <span className="font-medium text-slate-900">
                        {Number(summary.current.temp_min_c).toFixed(0)}°C
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-sm">
                      <Droplets className="h-4 w-4 text-blue-500" />
                      <span className="text-slate-600">Humidity:</span>
                      <span className="font-medium text-slate-900">
                        {Number(summary.current.humidity_pct).toFixed(0)}%
                      </span>
                    </div>
                  </div>

                  {/* Wind + sun */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm">
                      <Wind className="h-4 w-4 text-slate-500" />
                      <span className="text-slate-600">Wind:</span>
                      <span className="font-medium text-slate-900">
                        {Number(summary.current.wind_speed_kmph).toFixed(0)} km/h
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-sm">
                      <CloudRain className="h-4 w-4 text-blue-500" />
                      <span className="text-slate-600">Rain:</span>
                      <span className="font-medium text-slate-900">
                        {Number(summary.current.precipitation_mm).toFixed(1)} mm
                      </span>
                    </div>
                    {summary.current.sunrise_at && (
                      <div className="flex items-center gap-2 text-sm">
                        <Sunrise className="h-4 w-4 text-amber-500" />
                        <span className="text-slate-600">Sunrise:</span>
                        <span className="font-medium text-slate-900">
                          {new Date(summary.current.sunrise_at).toLocaleTimeString("en-IN", {
                            hour: "2-digit",
                            minute: "2-digit",
                            hour12: true,
                          })}
                        </span>
                      </div>
                    )}
                    {summary.current.sunset_at && (
                      <div className="flex items-center gap-2 text-sm">
                        <Sunset className="h-4 w-4 text-orange-500" />
                        <span className="text-slate-600">Sunset:</span>
                        <span className="font-medium text-slate-900">
                          {new Date(summary.current.sunset_at).toLocaleTimeString("en-IN", {
                            hour: "2-digit",
                            minute: "2-digit",
                            hour12: true,
                          })}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Advisory */}
                {summary.current.agromet_advisory && (
                  <div className="mt-4 rounded-md bg-blue-50 p-3">
                    <p className="text-xs font-medium text-blue-900">
                      Agromet Advisory
                    </p>
                    <p className="mt-1 text-sm text-blue-800">
                      {summary.current.agromet_advisory}
                    </p>
                  </div>
                )}

                {/* Source attribution */}
                <div className="mt-3 text-xs text-slate-400">
                  Source: {summary.current.source} · Plot: {summary.plot_name}
                </div>
              </CardContent>
            </Card>

            {/* 7-day forecast */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Calendar className="h-5 w-5 text-primary" />
                  7-Day Forecast
                </CardTitle>
                <CardDescription>
                  Issued {formatDateTime(summary.forecast[0]?.source ? new Date().toISOString() : "")}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
                  {summary.forecast.map((day) => (
                    <ForecastDay key={day.forecast_date} day={day} />
                  ))}
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </main>
    </div>
  );
}

function Header() {
  const { user, logout } = useAuthStore();
  const router = useRouter();
  const handleLogout = async () => {
    await logout();
    router.push("/");
  };
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/dashboard" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary">
            <Sprout className="h-5 w-5 text-white" />
          </div>
          <span className="text-lg font-bold text-slate-900">KrishiSetu</span>
        </Link>
        <div className="flex items-center gap-3">
          <span className="hidden text-sm font-medium text-slate-700 sm:block">
            {user?.full_name}
          </span>
          <Button variant="ghost" size="sm" onClick={handleLogout}>
            Logout
          </Button>
        </div>
      </div>
    </header>
  );
}

function AlertCard({ alert }: { alert: WeatherAlert }) {
  const color = ALERT_SEVERITY_COLORS[alert.severity];
  return (
    <div className={`rounded-md border p-4 ${color}`}>
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">{alert.title}</h3>
            <span className="text-xs uppercase font-bold">
              {alert.severity}
            </span>
          </div>
          <p className="mt-1 text-sm opacity-90">{alert.description}</p>
          <p className="mt-1 text-xs opacity-75">
            Effective: {formatDateTime(alert.effective_at)} —{" "}
            Expires: {formatDateTime(alert.expires_at)}
          </p>
          {alert.recommended_actions && (
            <div className="mt-3 rounded bg-white/40 p-2">
              <p className="text-xs font-medium">Recommended Actions:</p>
              <p className="mt-1 text-xs">{alert.recommended_actions}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ForecastDay({ day }: { day: DailyForecast }) {
  const date = new Date(day.forecast_date);
  const dayName = date.toLocaleDateString("en-IN", { weekday: "short" });
  const dateStr = date.toLocaleDateString("en-IN", { day: "numeric", month: "short" });

  return (
    <div className="rounded-md border border-slate-200 p-3 text-center">
      <div className="text-xs font-medium text-slate-600">{dayName}</div>
      <div className="text-xs text-slate-400">{dateStr}</div>
      <div className="my-2 text-3xl">
        {WEATHER_ICONS[day.weather_main] || "🌡️"}
      </div>
      <div className="text-sm font-semibold text-slate-900">
        {Number(day.temp_max_c).toFixed(0)}°C
      </div>
      <div className="text-xs text-slate-500">
        {Number(day.temp_min_c).toFixed(0)}°C
      </div>
      <div className="mt-1 flex items-center justify-center gap-1 text-xs text-blue-600">
        <Droplets className="h-3 w-3" />
        {Number(day.precipitation_probability).toFixed(0)}%
      </div>
    </div>
  );
}
