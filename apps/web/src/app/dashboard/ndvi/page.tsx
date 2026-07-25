"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Satellite,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  Loader2,
  Sprout,
  MapPin,
  CheckCircle2,
  Droplets,
  Cloud,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { ndviApi } from "@/lib/api/ndvi";
import { plotApi } from "@/lib/api/plots";
import type {
  PlotNDVISummary,
  PlotListResponse,
  NDVIAnomalyAlert,
} from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatDateTime } from "@/lib/utils";

const HEALTH_COLORS = {
  healthy: { bg: "bg-green-50", text: "text-green-700", border: "border-green-200", label: "Healthy" },
  moderate: { bg: "bg-yellow-50", text: "text-yellow-700", border: "border-yellow-200", label: "Moderate" },
  sparse: { bg: "bg-orange-50", text: "text-orange-700", border: "border-orange-200", label: "Sparse" },
  bare: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200", label: "Bare Soil" },
} as const;

const ANOMALY_SEVERITY = {
  severe_drop: { label: "Severe Drop", color: "bg-red-50 text-red-700 border-red-200" },
  significant_drop: { label: "Significant Drop", color: "bg-orange-50 text-orange-700 border-orange-200" },
  low_vegetation: { label: "Low Vegetation", color: "bg-amber-50 text-amber-700 border-amber-200" },
  prolonged_decline: { label: "Prolonged Decline", color: "bg-amber-50 text-amber-700 border-amber-200" },
} as const;

export default function NDVIPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const [plots, setPlots] = useState<PlotListResponse | null>(null);
  const [selectedPlotId, setSelectedPlotId] = useState<string | null>(null);
  const [summary, setSummary] = useState<PlotNDVISummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
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
      } else {
        setIsLoading(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load plots");
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!selectedPlotId) return;
    loadSummary();
  }, [selectedPlotId]);

  async function loadSummary() {
    if (!selectedPlotId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await ndviApi.getPlotSummary(selectedPlotId);
      setSummary(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load NDVI data");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleRefresh() {
    if (!selectedPlotId || isRefreshing) return;
    setIsRefreshing(true);
    setError(null);
    try {
      const result = await ndviApi.refreshPlot(selectedPlotId);
      if (result.message) {
        // Show info message (skipped case)
        setError(result.message);
      }
      // Reload summary
      await loadSummary();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh NDVI");
    } finally {
      setIsRefreshing(false);
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
            <h1 className="text-2xl font-bold text-slate-900">NDVI Monitoring</h1>
            <p className="text-sm text-slate-600">
              Satellite-based vegetation health monitoring for your plots
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
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleRefresh}
                  disabled={isRefreshing}
                >
                  <RefreshCw className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
                  {isRefreshing ? "Refreshing..." : "Refresh NDVI"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {plots && plots.plots.length === 0 && (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <MapPin className="h-12 w-12 text-slate-300" />
              <p className="mt-3 text-sm font-medium text-slate-900">No plots registered</p>
              <p className="mt-1 text-xs text-slate-500">
                Register a plot to enable NDVI monitoring.
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
          <Card className="mb-6 border-amber-200">
            <CardContent className="p-4">
              <p className="text-sm text-amber-700">{error}</p>
            </CardContent>
          </Card>
        )}

        {summary && (
          <>
            {/* Active anomalies */}
            {summary.active_anomalies.length > 0 && (
              <div className="mb-6 space-y-3">
                {summary.active_anomalies.map((alert) => (
                  <AnomalyAlertCard
                    key={alert.id}
                    alert={alert}
                    onAcknowledge={async (notes) => {
                      await ndviApi.acknowledgeAnomaly(alert.id, notes);
                      await loadSummary();
                    }}
                  />
                ))}
              </div>
            )}

            {/* Latest NDVI */}
            {summary.latest_observation ? (
              <div className="grid gap-6 lg:grid-cols-3">
                {/* Main NDVI value */}
                <Card className="lg:col-span-1">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Satellite className="h-5 w-5 text-primary" />
                      Latest NDVI
                    </CardTitle>
                    <CardDescription>
                      {formatDateTime(summary.latest_observation.observed_at)}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {(() => {
                      const health = summary.latest_observation.health_category;
                      const colors = HEALTH_COLORS[health];
                      const ndvi = Number(summary.latest_observation.ndvi_mean);
                      return (
                        <div className={`rounded-lg border-2 p-6 text-center ${colors.border} ${colors.bg}`}>
                          <div className="text-5xl font-bold text-slate-900">
                            {ndvi.toFixed(3)}
                          </div>
                          <div className={`mt-2 inline-flex items-center gap-1 rounded-full px-3 py-1 text-sm font-medium ${colors.text}`}>
                            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: getColorForHealth(health) }} />
                            {colors.label}
                          </div>
                          <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
                            <div>
                              <p className="text-slate-500">Min</p>
                              <p className="font-semibold text-slate-900">
                                {Number(summary.latest_observation.ndvi_min).toFixed(3)}
                              </p>
                            </div>
                            <div>
                              <p className="text-slate-500">Mean</p>
                              <p className="font-semibold text-slate-900">
                                {Number(summary.latest_observation.ndvi_mean).toFixed(3)}
                              </p>
                            </div>
                            <div>
                              <p className="text-slate-500">Max</p>
                              <p className="font-semibold text-slate-900">
                                {Number(summary.latest_observation.ndvi_max).toFixed(3)}
                              </p>
                            </div>
                          </div>
                        </div>
                      );
                    })()}
                    <div className="mt-4 space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1 text-slate-500">
                          <Cloud className="h-3 w-3" />
                          Cloud cover
                        </span>
                        <span className={`font-medium ${summary.latest_observation.is_cloudy ? "text-amber-600" : "text-green-600"}`}>
                          {Number(summary.latest_observation.cloud_cover_pct).toFixed(1)}%
                          {summary.latest_observation.is_cloudy && " (cloudy)"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1 text-slate-500">
                          <Droplets className="h-3 w-3" />
                          Valid pixels
                        </span>
                        <span className="font-medium text-slate-700">
                          {summary.latest_observation.valid_pixel_count} / {summary.latest_observation.total_pixel_count}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-slate-500">Source</span>
                        <span className="font-medium text-slate-700 capitalize">
                          {summary.latest_observation.source}
                        </span>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Trend */}
                <Card className="lg:col-span-2">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <TrendingUp className="h-5 w-5 text-primary" />
                      Vegetation Trend
                    </CardTitle>
                    <CardDescription>
                      NDVI change over recent observations
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <TrendDisplay
                      trend={summary.trend}
                      change={summary.trend_change}
                      current={summary.latest_observation?.ndvi_mean}
                      previous={summary.previous_observation?.ndvi_mean}
                    />

                    {/* Time series chart */}
                    {summary.history.length > 0 && (
                      <div className="mt-6">
                        <h4 className="mb-3 text-sm font-semibold text-slate-900">
                          NDVI History ({summary.history.length} observations)
                        </h4>
                        <NDVIChart observations={summary.history} />
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            ) : (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-12">
                  <Satellite className="h-12 w-12 text-slate-300" />
                  <p className="mt-3 text-sm font-medium text-slate-900">
                    No NDVI data yet
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Click &quot;Refresh NDVI&quot; to fetch the latest satellite imagery
                    and compute vegetation health for this plot.
                  </p>
                  <Button
                    onClick={handleRefresh}
                    disabled={isRefreshing}
                    className="mt-4"
                  >
                    <RefreshCw className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
                    {isRefreshing ? "Computing NDVI..." : "Compute NDVI Now"}
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* NDVI color scale legend */}
            {summary.latest_observation && (
              <Card className="mt-6">
                <CardHeader>
                  <CardTitle className="text-base">NDVI Color Scale</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-1">
                    <div className="flex-1">
                      <div className="flex h-6 overflow-hidden rounded-md">
                        <div className="flex-1" style={{ backgroundColor: "#1E40AF" }} />
                        <div className="flex-1" style={{ backgroundColor: "#DC2626" }} />
                        <div className="flex-1" style={{ backgroundColor: "#FF9800" }} />
                        <div className="flex-1" style={{ backgroundColor: "#FFEB3B" }} />
                        <div className="flex-1" style={{ backgroundColor: "#4CAF50" }} />
                        <div className="flex-1" style={{ backgroundColor: "#2E7D32" }} />
                      </div>
                      <div className="mt-1 flex justify-between text-xs text-slate-500">
                        <span>-1.0</span>
                        <span>0.0</span>
                        <span>+1.0</span>
                      </div>
                    </div>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                    <div className="flex items-center gap-1">
                      <span className="h-3 w-3 rounded" style={{ backgroundColor: "#2E7D32" }} />
                      <span className="text-slate-600">Healthy (0.6+)</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="h-3 w-3 rounded" style={{ backgroundColor: "#FFEB3B" }} />
                      <span className="text-slate-600">Moderate (0.3-0.6)</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="h-3 w-3 rounded" style={{ backgroundColor: "#FF9800" }} />
                      <span className="text-slate-600">Sparse (0.1-0.3)</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="h-3 w-3 rounded" style={{ backgroundColor: "#DC2626" }} />
                      <span className="text-slate-600">Bare (&lt;0.1)</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
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

function TrendDisplay({
  trend,
  change,
  current,
  previous,
}: {
  trend: string;
  change: number | null;
  current?: number;
  previous?: number;
}) {
  const icons = {
    improving: <TrendingUp className="h-5 w-5 text-green-600" />,
    declining: <TrendingDown className="h-5 w-5 text-red-600" />,
    stable: <Minus className="h-5 w-5 text-slate-500" />,
    insufficient_data: <Minus className="h-5 w-5 text-slate-400" />,
  };
  const colors = {
    improving: "bg-green-50 text-green-700 border-green-200",
    declining: "bg-red-50 text-red-700 border-red-200",
    stable: "bg-slate-50 text-slate-700 border-slate-200",
    insufficient_data: "bg-slate-50 text-slate-500 border-slate-200",
  };
  const labels = {
    improving: "Improving",
    declining: "Declining",
    stable: "Stable",
    insufficient_data: "Insufficient data",
  };

  return (
    <div className={`rounded-md border p-4 ${colors[trend as keyof typeof colors]}`}>
      <div className="flex items-center gap-3">
        {icons[trend as keyof typeof icons]}
        <div>
          <p className="font-semibold">{labels[trend as keyof typeof labels]}</p>
          {change !== null && (
            <p className="text-sm">
              {change > 0 ? "+" : ""}{change.toFixed(3)} NDVI change
            </p>
          )}
        </div>
      </div>
      {previous !== undefined && current !== undefined && (
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
          <div className="rounded bg-white/50 p-2">
            <p className="text-slate-500">Previous</p>
            <p className="font-semibold">{Number(previous).toFixed(3)}</p>
          </div>
          <div className="rounded bg-white/50 p-2">
            <p className="text-slate-500">Current</p>
            <p className="font-semibold">{Number(current).toFixed(3)}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function NDVIChart({ observations }: { observations: import("@/lib/api/types").NDVIObservation[] }) {
  // Reverse to show oldest → newest (left to right)
  const sorted = [...observations].reverse();

  // Calculate chart dimensions
  const width = 600;
  const height = 200;
  const padding = 40;
  const chartWidth = width - 2 * padding;
  const chartHeight = height - 2 * padding;

  // Y-axis: NDVI range [-0.2, 1.0]
  const yMin = -0.2;
  const yMax = 1.0;
  const yRange = yMax - yMin;

  // Map data points to chart coordinates
  const points = sorted.map((obs, i) => {
    const x = padding + (i / Math.max(1, sorted.length - 1)) * chartWidth;
    const y = padding + chartHeight - ((Number(obs.ndvi_mean) - yMin) / yRange) * chartHeight;
    return { x, y, obs };
  });

  // Build path
  const pathData = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(" ");

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ minWidth: 400 }}>
        {/* Y-axis grid lines */}
        {[0.0, 0.2, 0.4, 0.6, 0.8, 1.0].map((val) => {
          const y = padding + chartHeight - ((val - yMin) / yRange) * chartHeight;
          return (
            <g key={val}>
              <line
                x1={padding}
                y1={y}
                x2={width - padding}
                y2={y}
                stroke="#E2E8F0"
                strokeWidth={1}
                strokeDasharray="2 2"
              />
              <text x={padding - 5} y={y + 4} textAnchor="end" className="fill-slate-500 text-[10px]">
                {val.toFixed(1)}
              </text>
            </g>
          );
        })}

        {/* Health zone backgrounds */}
        <rect
          x={padding}
          y={padding + chartHeight - ((1.0 - yMin) / yRange) * chartHeight}
          width={chartWidth}
          height={((0.6 - yMin) / yRange) * chartHeight}
          fill="#4CAF50"
          opacity={0.05}
        />

        {/* Line path */}
        {points.length > 1 && (
          <path
            d={pathData}
            fill="none"
            stroke="#4CAF50"
            strokeWidth={2}
          />
        )}

        {/* Data points */}
        {points.map((p, i) => (
          <g key={i}>
            <circle
              cx={p.x}
              cy={p.y}
              r={4}
              fill={getColorForHealth(p.obs.health_category)}
              stroke="white"
              strokeWidth={2}
            />
          </g>
        ))}

        {/* X-axis labels (every other point to avoid clutter) */}
        {points.map((p, i) => {
          if (i % 2 !== 0 && i !== points.length - 1) return null;
          const date = new Date(p.obs.observed_at);
          return (
            <text
              key={i}
              x={p.x}
              y={height - padding + 15}
              textAnchor="middle"
              className="fill-slate-500 text-[9px]"
            >
              {date.toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

function AnomalyAlertCard({
  alert,
  onAcknowledge,
}: {
  alert: NDVIAnomalyAlert;
  onAcknowledge: (notes?: string) => Promise<void>;
}) {
  const severity = ANOMALY_SEVERITY[alert.anomaly_type];
  const [showResolveForm, setShowResolveForm] = useState(false);
  const [resolutionNotes, setResolutionNotes] = useState("");

  return (
    <div className={`rounded-md border p-4 ${severity.color}`}>
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">
              NDVI {severity.label} Detected
            </h3>
            <span className="text-xs uppercase font-bold">
              {alert.drop_percentage.toFixed(1)}% drop
            </span>
          </div>
          <p className="mt-1 text-sm">
            NDVI dropped from <strong>{Number(alert.previous_ndvi).toFixed(3)}</strong> to{" "}
            <strong>{Number(alert.current_ndvi).toFixed(3)}</strong> (change of{" "}
            {Number(alert.drop_magnitude).toFixed(3)})
          </p>
          <p className="mt-1 text-xs opacity-75">
            Detected {formatDateTime(alert.created_at)}
          </p>
          <div className="mt-3 flex gap-2">
            {alert.status === "active" && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => onAcknowledge()}
              >
                <CheckCircle2 className="h-4 w-4" />
                Acknowledge
              </Button>
            )}
            {alert.status !== "resolved" && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowResolveForm(!showResolveForm)}
              >
                Resolve
              </Button>
            )}
          </div>
          {showResolveForm && (
            <div className="mt-3 space-y-2">
              <textarea
                value={resolutionNotes}
                onChange={(e) => setResolutionNotes(e.target.value)}
                placeholder="What action did you take? (e.g., applied fungicide, harvested, etc.)"
                className="flex min-h-[60px] w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm"
              />
              <Button
                size="sm"
                onClick={() => onAcknowledge(resolutionNotes || undefined)}
              >
                Mark Resolved
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function getColorForHealth(health: string): string {
  return {
    healthy: "#4CAF50",
    moderate: "#FFEB3B",
    sparse: "#FF9800",
    bare: "#DC2626",
  }[health] || "#9CA3AF";
}
